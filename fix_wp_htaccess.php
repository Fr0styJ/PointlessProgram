<?php
require('/var/www/html/wp-load.php');

// The .htaccess needs the WordPress rewrite rules for pretty permalinks to work
// flush_rewrite_rules() with true parameter writes them to .htaccess
// But we need AllowOverride All in Apache config first

// Write the proper rewrite rules directly to .htaccess
$htaccess = <<<'HTACCESS'
# BEGIN WordPress
# The directives (lines) between "BEGIN WordPress" and "END WordPress" are
# dynamically generated, and should only be modified via WordPress filters.
# Any changes to the directives between these markers will be overwritten.
<IfModule mod_rewrite.c>
RewriteEngine On
RewriteRule .* - [E=HTTP_AUTHORIZATION:%{HTTP:Authorization}]
RewriteBase /
RewriteRule ^index\.php$ - [L]
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule . /index.php [L]
</IfModule>
# END WordPress
HTACCESS;

file_put_contents('/var/www/html/.htaccess', $htaccess);
echo "Wrote .htaccess\n";
echo "Contents:\n";
echo file_get_contents('/var/www/html/.htaccess');
