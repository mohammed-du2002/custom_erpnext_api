<?php

namespace App\Providers;

use CustomErpnext\Laravel\ErpNextClient;
use CustomErpnext\Laravel\Services\PullApi;
use CustomErpnext\Laravel\Services\PushApi;
use Illuminate\Support\ServiceProvider;

/**
 * Copy to app/Providers/ErpNextServiceProvider.php and register in bootstrap/providers.php or config/app.php.
 */
class ErpNextServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        $this->mergeConfigFrom(
            base_path('config/erpnext.php'),
            'erpnext'
        );

        $this->app->singleton(ErpNextClient::class, fn () => ErpNextClient::fromConfig());
        $this->app->singleton(PullApi::class, fn ($app) => new PullApi($app->make(ErpNextClient::class)));
        $this->app->singleton(PushApi::class, fn ($app) => new PushApi($app->make(ErpNextClient::class)));
    }
}
