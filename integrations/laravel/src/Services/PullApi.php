<?php

namespace CustomErpnext\Laravel\Services;

use CustomErpnext\Laravel\ErpNextClient;

class PullApi
{
    public function __construct(protected ErpNextClient $client) {}

    public function healthCheck(?string $requestId = null): array
    {
        return $this->client->pull('health_check', [], $requestId);
    }

    public function getItemsForPos(
        string $branch,
        ?string $modifiedFrom = null,
        int $page = 1,
        int $pageSize = 100,
        ?string $priceList = null,
        ?string $requestId = null,
    ): array {
        return $this->client->pull('get_items_for_pos', array_filter([
            'branch' => $branch,
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
            'price_list' => $priceList,
        ], fn ($value) => $value !== null), $requestId);
    }

    public function pullItems(?string $modifiedFrom = null, int $page = 1, int $pageSize = 100): array
    {
        return $this->client->pull('pull_items', array_filter([
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullItemGroups(
        ?string $groupType = null,
        ?string $modifiedFrom = null,
        int $page = 1,
        int $pageSize = 100,
    ): array {
        return $this->client->pull('pull_item_groups', array_filter([
            'group_type' => $groupType,
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullItemPrices(?string $company = null, ?string $modifiedFrom = null, int $page = 1, int $pageSize = 200): array
    {
        return $this->client->pull('pull_item_prices', array_filter([
            'company' => $company,
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullCustomers(
        ?string $company = null,
        ?string $branch = null,
        ?string $modifiedFrom = null,
        int $page = 1,
        int $pageSize = 100,
    ): array {
        return $this->client->pull('pull_customers', array_filter([
            'company' => $company,
            'branch' => $branch,
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullTaxTemplates(?string $modifiedFrom = null, int $page = 1, int $pageSize = 50): array
    {
        return $this->client->pull('pull_tax_templates', array_filter([
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullWarehouses(
        ?string $company = null,
        ?string $branch = null,
        ?string $modifiedFrom = null,
        int $page = 1,
        int $pageSize = 50,
    ): array {
        return $this->client->pull('pull_warehouses', array_filter([
            'company' => $company,
            'branch' => $branch,
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullStock(
        ?string $warehouse = null,
        ?string $branch = null,
        ?string $modifiedFrom = null,
        int $page = 1,
        int $pageSize = 200,
    ): array {
        return $this->client->pull('pull_stock', array_filter([
            'warehouse' => $warehouse,
            'branch' => $branch,
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullPromotions(?string $branch = null, ?string $modifiedFrom = null, int $page = 1, int $pageSize = 50): array
    {
        return $this->client->pull('pull_promotions', array_filter([
            'branch' => $branch,
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullBranches(?string $company = null, ?string $modifiedFrom = null): array
    {
        return $this->client->pull('pull_branches', array_filter([
            'company' => $company,
            'modified_from' => $modifiedFrom,
        ], fn ($value) => $value !== null));
    }

    public function pullPosDevices(?string $branch = null, ?string $modifiedFrom = null): array
    {
        return $this->client->pull('pull_pos_devices', array_filter([
            'branch' => $branch,
            'modified_from' => $modifiedFrom,
        ], fn ($value) => $value !== null));
    }

    public function pullDiscounts(
        ?string $branch = null,
        ?string $modifiedFrom = null,
        int $page = 1,
        int $pageSize = 100,
    ): array {
        return $this->client->pull('pull_discounts', array_filter([
            'branch' => $branch,
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullEmployees(
        ?string $company = null,
        ?string $branch = null,
        ?string $modifiedFrom = null,
        int $page = 1,
        int $pageSize = 100,
    ): array {
        return $this->client->pull('pull_employees', array_filter([
            'company' => $company,
            'branch' => $branch,
            'modified_from' => $modifiedFrom,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null));
    }

    public function pullCashierShifts(
        ?string $branch = null,
        ?string $posDevice = null,
        ?string $status = null,
        ?string $modifiedFrom = null,
        int $includeMovements = 0,
        int $page = 1,
        int $pageSize = 50,
        ?string $requestId = null,
    ): array {
        return $this->client->pull('pull_cashier_shifts', array_filter([
            'branch' => $branch,
            'pos_device' => $posDevice,
            'status' => $status,
            'modified_from' => $modifiedFrom,
            'include_movements' => $includeMovements,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null), $requestId);
    }

    public function pullSystemSettings(
        ?string $branch = null,
        ?string $company = null,
        ?string $modifiedFrom = null,
        ?string $requestId = null,
    ): array {
        return $this->client->pull('pull_system_settings', array_filter([
            'branch' => $branch,
            'company' => $company,
            'modified_from' => $modifiedFrom,
        ], fn ($value) => $value !== null), $requestId);
    }

    public function fullSync(
        string $branch,
        ?string $priceList = null,
        int $page = 1,
        int $pageSize = 500,
        ?string $requestId = null,
    ): array {
        return $this->client->pull('full_sync', array_filter([
            'branch' => $branch,
            'price_list' => $priceList,
            'page' => $page,
            'page_size' => $pageSize,
        ], fn ($value) => $value !== null), $requestId);
    }
}
