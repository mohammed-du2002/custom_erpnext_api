<?php

namespace CustomErpnext\Laravel;

use RuntimeException;

class ErpNextException extends RuntimeException
{
    public function __construct(
        string $message,
        public readonly ?string $code = null,
        public readonly int $httpStatus = 400,
        public readonly array $errors = [],
    ) {
        parent::__construct($message, $httpStatus);
    }

    public static function fromResponse(array $body, int $httpStatus): self
    {
        $errors = $body['errors'] ?? [];
        $first = $errors[0] ?? [];
        $message = $first['message'] ?? 'ERPNext request failed';
        $code = $first['code'] ?? null;

        return new self($message, $code, $httpStatus, $errors);
    }
}
