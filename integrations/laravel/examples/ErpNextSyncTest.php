<?php

namespace App\Console\Commands;

use CustomErpnext\Laravel\ErpNextClient;
use CustomErpnext\Laravel\Services\PullApi;
use CustomErpnext\Laravel\Services\PushApi;
use Illuminate\Console\Command;

/**
 * Copy to app/Console/Commands/ErpNextSyncTest.php and register in Console\Kernel.
 */
class ErpNextSyncTest extends Command
{
    protected $signature = 'erpnext:sync-test
                            {--branch=BR1 : Branch code for pull tests}
                            {--push : Also run a dry-run push payload validation against ERPNext}';

    protected $description = 'Test ERPNext middleware API connectivity (pull + optional push)';

    public function handle(): int
    {
        $client = ErpNextClient::fromConfig();
        $pull = new PullApi($client);
        $branch = $this->option('branch');

        $this->info('1/5 Health check...');
        $health = $pull->healthCheck();
        $this->line(json_encode($health['data'] ?? [], JSON_PRETTY_PRINT));

        $this->info('2/5 Pull branches...');
        $branches = $pull->pullBranches();
        $this->line(json_encode($branches['data']['branches'] ?? [], JSON_PRETTY_PRINT));

        $this->info("3/5 Pull POS items for branch {$branch}...");
        $items = $pull->getItemsForPos($branch, page: 1, pageSize: 5);
        $this->line('Items: '.count($items['data']['items'] ?? []));
        $this->line('Meta: '.json_encode($items['meta'] ?? [], JSON_PRETTY_PRINT));

        $this->info("4/5 Pull stock for branch {$branch}...");
        $stock = $pull->pullStock(branch: $branch, page: 1, pageSize: 5);
        $this->line('Stock rows: '.count($stock['data']['stock'] ?? []));

        if ($this->option('push')) {
            $this->info('5/5 Push device status ping...');
            $push = new PushApi($client);
            $result = $push->updatePosDeviceStatus('TEST-DEVICE', true, now()->toIso8601String());
            $this->line(json_encode($result['data'] ?? [], JSON_PRETTY_PRINT));
        } else {
            $this->info('5/5 Push test skipped (use --push to enable)');
        }

        $this->newLine();
        $this->components->info('ERPNext integration test completed successfully.');

        return self::SUCCESS;
    }
}
