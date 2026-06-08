<?php

namespace CustomErpnext\Laravel;

use Illuminate\Http\Client\PendingRequest;
use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class ErpNextClient
{
    public function __construct(
        protected string $baseUrl,
        protected string $apiKey,
        protected string $apiSecret,
        protected bool $signRequests = true,
        protected int $timeout = 30,
        protected int $retryTimes = 3,
        protected int $retrySleepMs = 500,
    ) {
        $this->baseUrl = rtrim($baseUrl, '/');
    }

    public static function fromConfig(?array $config = null): self
    {
        $config ??= config('erpnext');

        return new self(
            baseUrl: $config['base_url'],
            apiKey: $config['api_key'],
            apiSecret: $config['api_secret'],
            signRequests: (bool) ($config['sign_requests'] ?? true),
            timeout: (int) ($config['timeout'] ?? 30),
            retryTimes: (int) ($config['retry_times'] ?? 3),
            retrySleepMs: (int) ($config['retry_sleep_ms'] ?? 500),
        );
    }

    public function call(string $method, array $params = [], ?string $requestId = null): array
    {
        $requestId ??= (string) Str::uuid();
        $body = json_encode($params, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $endpoint = $this->baseUrl.'/api/method/'.$method;

        $response = $this->signedRequest($requestId, $body)
            ->withBody($body, 'application/json')
            ->post($endpoint);

        return $this->parseResponse($response);
    }

    public function pull(string $method, array $params = [], ?string $requestId = null): array
    {
        return $this->call('custom_erpnext.api.v1.pull.'.$method, $params, $requestId);
    }

    public function push(string $method, array $params = [], ?string $requestId = null): array
    {
        return $this->call('custom_erpnext.api.v1.push.'.$method, $params, $requestId);
    }

    protected function signedRequest(string $requestId, string $rawBody): PendingRequest
    {
        $headers = [
            'Authorization' => 'token '.$this->apiKey.':'.$this->apiSecret,
            'Accept' => 'application/json',
            'Content-Type' => 'application/json',
            'X-Request-ID' => $requestId,
        ];

        if ($this->signRequests && $this->apiSecret !== '') {
            $timestamp = (string) time();
            $headers['X-Timestamp'] = $timestamp;
            $headers['X-Signature'] = hash_hmac('sha256', $timestamp.'.'.$rawBody, $this->apiSecret);
        }

        return Http::timeout($this->timeout)
            ->retry($this->retryTimes, $this->retrySleepMs, throw: false)
            ->withHeaders($headers)
            ->asJson();
    }

    protected function parseResponse(Response $response): array
    {
        $body = $response->json() ?? [];
        $message = $body['message'] ?? $body;

        if (! is_array($message)) {
            throw new ErpNextException('Unexpected ERPNext response format', httpStatus: $response->status());
        }

        if (($message['success'] ?? null) === false) {
            throw ErpNextException::fromResponse($message, $response->status());
        }

        if (! $response->successful()) {
            throw ErpNextException::fromResponse(
                $message,
                $response->status() ?: 500,
            );
        }

        return $message;
    }
}
