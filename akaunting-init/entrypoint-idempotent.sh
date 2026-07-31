#!/bin/bash -e
# Wraps the stock akaunting/akaunting entrypoint (/usr/local/bin/akaunting.sh) to make
# AKAUNTING_SETUP=true safe across container restarts AND recreations.
#
# The vendor entrypoint unconditionally re-runs `php artisan install` whenever
# AKAUNTING_SETUP=true, with no check for an existing install. `php artisan install`
# is not idempotent end-to-end: it (1) writes .env from env vars, (2) runs migrations
# + permission seeding, then (3) creates the company + admin user inside one DB
# transaction. Steps 1-2 are safe to repeat; step 3 errors ("Not able to create a new
# user.") once those rows exist and rolls the whole command back — including the
# otherwise-harmless .env write.
#
# The app container's filesystem (.env, APP_KEY) is NOT on a persistent volume while
# the DB is, so two distinct restart scenarios exist:
#   - same container restarts (crash, `docker restart`, host reboot): filesystem is
#     unchanged, .env from the original install is still there and already correct.
#     We just need to skip re-running install so it doesn't crash-loop.
#   - container recreated (`docker compose up` after a config change, image update)
#     against an already-populated DB: filesystem is fresh, .env does NOT exist, but
#     we must not touch the company/admin rows again. We still need steps 1-2.
cd /var/www/html

if [ -f .env ] && grep -q '^APP_INSTALLED=true' .env; then
    echo "akaunting-init: existing .env already marks this install complete, starting apache only"
    unset AKAUNTING_SETUP
    exec /usr/local/bin/akaunting.sh --start
fi

DB_HAS_DATA=false
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
    DB_HAS_DATA=true
fi

if [ "$DB_HAS_DATA" = "false" ]; then
    echo "akaunting-init: no existing schema found, running first-time install"
    exec /usr/local/bin/akaunting.sh --setup
fi

echo "akaunting-init: schema already populated but .env missing (container recreated) — rewriting .env/running migrations without touching company/admin rows"

php artisan tinker --execute='
    App\Utilities\Installer::createDefaultEnvFile();
    $ok = App\Utilities\Installer::createDbTables(
        getenv("DB_HOST"), getenv("DB_PORT"), getenv("DB_NAME"),
        getenv("DB_USERNAME"), getenv("DB_PASSWORD"), getenv("DB_PREFIX")
    );
    if (!$ok) {
        fwrite(STDERR, "akaunting-init: could not connect to database to rewrite .env\n");
        exit(1);
    }
    App\Utilities\Installer::finalTouches();
    echo "akaunting-init: env rewritten\n";
'

a2enmod rewrite
mkdir -p storage/framework/{sessions,views,cache}
mkdir -p storage/app/uploads
chmod -R u=rwX,g=rX,o=rX /var/www/html
chown -R www-data:root /var/www/html

exec docker-php-entrypoint apache2-foreground
