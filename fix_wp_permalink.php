<?php
require('/var/www/html/wp-load.php');

// Check current permalink structure
$current = get_option('permalink_structure');
echo "Current permalink_structure: '" . $current . "'\n";

// Enable pretty permalinks (post name is good for REST API)
if (empty($current)) {
    update_option('permalink_structure', '/%postname%/');
    // Flush rewrite rules
    flush_rewrite_rules(true);
    echo "Set permalink_structure to /%postname%/\n";
} else {
    echo "Permalink structure already set, flushing rules.\n";
    flush_rewrite_rules(true);
}

// Check REST API  
$rest_url = get_rest_url();
echo "REST URL: $rest_url\n";

// Also check if Application Passwords are enabled
$enabled = get_option('wp_application_passwords');
echo "Application passwords enabled: " . ($enabled ? 'yes' : 'no/default') . "\n";

// Verify our app password - list them
$user = get_user_by('login', 'principal');
if ($user) {
    $app_passwords = WP_Application_Passwords::get_user_application_passwords($user->ID);
    echo "App passwords for principal: " . count($app_passwords) . "\n";
    foreach ($app_passwords as $ap) {
        echo "  - " . $ap['name'] . " (uuid: " . $ap['uuid'] . ")\n";
    }
}
