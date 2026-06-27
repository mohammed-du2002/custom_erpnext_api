<?php

namespace CustomErpnext\Laravel\Jobs;

use CustomErpnext\Laravel\ErpNextClient;
use CustomErpnext\Laravel\Services\PushApi;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Throwable;

/**
 * Push offline cashier movements from Laravel/SQLite to ERPNext.
 *
 * Copy to app/Jobs/PushCashierMovementsToErp.php and dispatch from your sync engine.
 */
class PushCashierMovementsToErp implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $tries = 3;

    public int $backoff = 30;

    public function __construct(
        public array $movements,
        public ?string $requestId = null,
    ) {
        $this->requestId ??= (string) Str::uuid();
        $this->onQueue('erp-sync');
    }

    public function handle(ErpNextClient $client): void
    {
        $push = new PushApi($client);
        $chunks = array_chunk($this->movements, 50);

        foreach ($chunks as $index => $chunk) {
            $requestId = $this->requestId.'-'.$index;
            $response = $push->syncCashierMovements($chunk, $requestId);
            $data = $response['data'] ?? $response['message']['data'] ?? [];

            if (! empty($data['queued'])) {
                Log::info('Cashier movements queued in ERPNext', [
                    'request_id' => $requestId,
                    'count' => $data['count'] ?? count($chunk),
                    'job_id' => $data['job_id'] ?? null,
                ]);
                continue;
            }

            foreach ($data['results'] ?? [] as $result) {
                if (($result['status'] ?? '') !== 'success') {
                    Log::warning('Cashier movement sync failed', [
                        'offline_movement_id' => $result['offline_movement_id'] ?? null,
                        'error' => $result['error'] ?? 'unknown',
                    ]);
                }
            }
        }
    }

    public function failed(Throwable $exception): void
    {
        Log::error('PushCashierMovementsToErp job failed', [
            'request_id' => $this->requestId,
            'movement_count' => count($this->movements),
            'error' => $exception->getMessage(),
        ]);
    }
}
