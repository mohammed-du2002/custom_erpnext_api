<?php

return [
    'base_url' => env('ERPNEXT_BASE_URL', 'http://tsc.localhost'),
    'api_key' => env('ERPNEXT_API_KEY'),
    'api_secret' => env('ERPNEXT_API_SECRET'),
    'sign_requests' => env('ERPNEXT_SIGN_REQUESTS', true),
    'timeout' => (int) env('ERPNEXT_TIMEOUT', 30),
    'retry_times' => (int) env('ERPNEXT_RETRY_TIMES', 3),
    'retry_sleep_ms' => (int) env('ERPNEXT_RETRY_SLEEP_MS', 500),
];
