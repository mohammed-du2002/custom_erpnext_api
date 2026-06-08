<?php

namespace CustomErpnext\Laravel\Services;

use CustomErpnext\Laravel\ErpNextClient;

class PushApi
{
    public function __construct(protected ErpNextClient $client) {}

    public function syncSalesInvoices(array $invoices, ?string $requestId = null): array
    {
        return $this->client->push('sync_sales_invoices', [
            'invoices' => $invoices,
            'request_id' => $requestId,
        ], $requestId);
    }

    public function syncDailySalesSummaries(array $summaries, ?string $requestId = null): array
    {
        return $this->client->push('sync_daily_sales_summaries', [
            'summaries' => $summaries,
            'request_id' => $requestId,
        ], $requestId);
    }

    public function updateStockQuantities(
        array $stockUpdates,
        ?string $warehouse = null,
        ?string $branch = null,
        ?string $requestId = null,
    ): array {
        return $this->client->push('update_stock_quantities', array_filter([
            'stock_updates' => $stockUpdates,
            'warehouse' => $warehouse,
            'branch' => $branch,
            'request_id' => $requestId,
        ], fn ($value) => $value !== null), $requestId);
    }

    public function updatePosDeviceStatus(
        string $deviceId,
        ?bool $isOnline = null,
        ?string $lastSyncTime = null,
        ?string $requestId = null,
    ): array {
        return $this->client->push('update_pos_device_status', array_filter([
            'device_id' => $deviceId,
            'is_online' => $isOnline === null ? null : ($isOnline ? 1 : 0),
            'last_sync_time' => $lastSyncTime,
        ], fn ($value) => $value !== null), $requestId);
    }
}
