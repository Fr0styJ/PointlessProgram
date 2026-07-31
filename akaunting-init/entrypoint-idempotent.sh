#!/bin/bash -e
# Wraps the stock akaunting/akaunting entrypoint (/usr/local/bin/akaunting.sh) to make
# AKAUNTING_SETUP=true safe across container restarts.
#
# The vendor entrypoint unconditionally re-runs `php artisan install` whenever
# AKAUNTING_SETUP=true, with no check for an existing install. `php artisan install`
# is not idempotent (it errors with "Not able to create a new user." once the admin
# user/company already exist), so any restart of an already-installed container
# (crash, host reboot, `docker restart`) puts it in a permanent crash loop and the
# appliance never serves traffic again. This wrapper checks whether the schema is
# already populated (via a plain PDO connection, before Laravel's own config/.env
# exist) and skips straight to `--start` if so.

cd /var/www/html

ALREADY_INSTALLED=false
if php -r '
    $h = getenv("DB_HOST"); $port = getenv("DB_PORT"); $db = getenv("DB_NAME");
    $u = getenv("DB_USERNAME"); $p = getenv("DB_PASSWORD"); $prefix = getenv("DB_PREFIX");
    try {
        $pdo = new PDO("mysql:host=$h;port=$port;dbname=$db", $u, $p);
        $pdo->query("SELECT 1 FROM `{$prefix}companies` LIMIT 1");
        exit(0);
    } catch (Throwable $e) {
        exit(1);
    }
' 2>/dev/null; then
    ALREADY_INSTALLED=true
fi

if [ "$ALREADY_INSTALLED" = "true" ]; then
    echo "akaunting-init: schema already populated, skipping install, starting apache only"
    # akaunting.sh decides whether to run `php artisan install` purely from
    # $AKAUNTING_SETUP, ignoring which flag (--start/--setup) it was called with —
    # so it must be unset here or --start would still re-run the (non-idempotent) install.
    unset AKAUNTING_SETUP
    exec /usr/local/bin/akaunting.sh --start
else
    echo "akaunting-init: no existing schema found, running first-time install"
    exec /usr/local/bin/akaunting.sh --setup
fi
