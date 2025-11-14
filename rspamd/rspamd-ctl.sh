#!/bin/bash
# Rspamd Docker Control Script
# Version: 2.0

COMPOSE_DIR="/opt/stalwart-rspamd"  # UPDATE THIS PATH

cd "$COMPOSE_DIR" || exit 1

case "$1" in
    --start|start)
        echo "Starting rspamd and redis..."
        docker compose up -d
        ;;
    --stop|stop)
        echo "Stopping rspamd and redis..."
        docker compose down
        ;;
    --restart|restart)
        echo "⚠ WARNING: Restarting will reload all configs from disk."
        echo "Consider using --reload instead for config changes."
        read -p "Continue with restart? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            echo "Restarting rspamd..."
            docker restart rspamd
            echo "Waiting for rspamd to start..."
            sleep 3
            echo "Reloading configuration..."
            docker exec rspamd rspamadm control reload
        else
            echo "Cancelled"
        fi
        ;;
    --reload|reload)
        echo "Reloading rspamd configuration (no downtime)..."
        docker exec rspamd rspamadm control reload
        echo ""
        echo "✓ Configuration reloaded successfully"
        ;;
    --status|status)
        echo "Container status:"
        docker ps --filter "name=rspamd" --filter "name=redis"
        echo ""
        echo "Rspamd workers:"
        docker exec rspamd rspamadm control stat 2>/dev/null || echo "Unable to get worker status"
        ;;
    --logs|logs)
        if [ -z "$2" ]; then
            docker logs rspamd --tail 50 -f
        else
            docker logs rspamd --tail "$2"
        fi
        ;;
    --test|test)
        echo "Testing configuration..."
        docker exec rspamd rspamadm configtest
        ;;
    --actions|actions)
        echo "Current action thresholds:"
        docker exec rspamd rspamadm configdump actions
        ;;
    --headers|headers)
        echo "Current milter_headers config:"
        docker exec rspamd rspamadm configdump milter_headers
        ;;
    --force-actions|force-actions)
        echo "Current force_actions config:"
        docker exec rspamd rspamadm configdump force_actions
        ;;
    --doctor|doctor)
        echo "=== Rspamd Health Check ==="
        echo ""
        echo "1. Container Status:"
        docker ps --filter "name=rspamd" --filter "name=redis" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        echo ""
        echo "2. Configuration Syntax:"
        if docker exec rspamd rspamadm configtest 2>&1 | grep -q "syntax OK"; then
            echo "   ✓ Configuration syntax is valid"
        else
            echo "   ✗ Configuration has syntax errors!"
            docker exec rspamd rspamadm configtest
        fi
        echo ""
        echo "3. Action Thresholds:"
        docker exec rspamd rspamadm configdump actions | grep -E "reject|greylist|add_header|rewrite_subject" | sed 's/^/   /'
        GREYLIST=$(docker exec rspamd rspamadm configdump actions | grep "greylist" | grep -oP '\d+')
        if [ "$GREYLIST" -lt 1000 ]; then
            echo "   ⚠ WARNING: greylist=$GREYLIST may cause email delays!"
        fi
        echo ""
        echo "4. Force Actions (Subject Rewrite Protection):"
        if docker exec rspamd rspamadm configdump force_actions 2>&1 | grep -q "never_rewrite_subject"; then
            echo "   ✓ Force actions rule is loaded"
            docker exec rspamd rspamadm configdump force_actions | grep -A 2 "never_rewrite_subject" | sed 's/^/   /'
        else
            echo "   ✗ Force actions rule NOT found - subject rewriting may occur!"
            echo "   Fix: Ensure override.d/force_actions.conf exists and reload"
        fi
        echo ""
        echo "5. Milter Headers Configuration:"
        if docker exec rspamd rspamadm configdump milter_headers | grep -q "all = true"; then
            echo "   ✗ WARNING: 'all = true' is set - this enables subject rewriting!"
            echo "   Fix: Remove 'all = true' from local.d/milter_headers.conf"
        else
            echo "   ✓ 'all = true' not found (good)"
        fi
        if docker exec rspamd rspamadm configdump milter_headers | grep -q "spam-header"; then
            echo "   ✗ WARNING: 'spam-header' in use array - may cause subject rewriting"
        else
            echo "   ✓ 'spam-header' not in use array (good)"
        fi
        echo ""
        echo "6. Redis Keys:"
        REDIS_KEYS=$(docker exec redis redis-cli KEYS "*" 2>/dev/null | wc -l)
        echo "   Redis has $REDIS_KEYS keys"
        if [ "$REDIS_KEYS" -gt 10 ]; then
            echo "   ⚠ Many keys in Redis - may contain old/override settings"
            echo "   Consider: $0 --clear-redis"
        fi
        echo ""
        echo "7. Recent Errors (last 50 lines):"
        ERROR_COUNT=$(docker logs rspamd --tail 50 2>&1 | grep -iE "error|warn|critical" | wc -l)
        if [ "$ERROR_COUNT" -gt 0 ]; then
            echo "   ⚠ Found $ERROR_COUNT warnings/errors:"
            docker logs rspamd --tail 50 2>&1 | grep -iE "error|warn|critical" | tail -5 | sed 's/^/   /'
            echo "   Run '$0 --logs 200' to see more details"
        else
            echo "   ✓ No recent errors found"
        fi
        echo ""
        echo "8. Configuration Files Present:"
        [ -f "./rspamd/local.d/actions.conf" ] && echo "   ✓ actions.conf" || echo "   ✗ actions.conf MISSING"
        [ -f "./rspamd/local.d/milter_headers.conf" ] && echo "   ✓ milter_headers.conf" || echo "   ✗ milter_headers.conf MISSING"
        [ -f "./rspamd/override.d/force_actions.conf" ] && echo "   ✓ force_actions.conf" || echo "   ✗ force_actions.conf MISSING"
        [ -f "./rspamd/local.d/redis.conf" ] && echo "   ✓ redis.conf" || echo "   ✗ redis.conf MISSING"
        [ -f "./rspamd/local.d/options.inc" ] && echo "   ✓ options.inc" || echo "   ⚠ options.inc not found (trusted_networks not configured)"
        echo ""
        echo "=== Health Check Complete ==="
        ;;
    --clear-redis|clear-redis)
        echo "WARNING: This will clear all Redis data!"
        echo "This removes dynamic settings that may override your configuration."
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            docker exec redis redis-cli FLUSHDB
            echo "Redis cleared. Restarting rspamd..."
            docker restart rspamd
            echo "Waiting for rspamd to start..."
            sleep 3
            echo "Reloading configuration..."
            docker exec rspamd rspamadm control reload
            echo ""
            echo "✓ Redis cleared, rspamd restarted, and config reloaded"
            echo "Run '$0 --doctor' to verify everything is working"
        else
            echo "Cancelled"
        fi
        ;;
    --shell|shell)
        docker exec -it rspamd /bin/sh
        ;;
    --redis-shell|redis-shell)
        docker exec -it redis redis-cli
        ;;
    --help|help|-h|"")
        echo "Rspamd Control Script v2.0"
        echo ""
        echo "Usage: $0 [--command]"
        echo ""
        echo "Daily Operations:"
        echo "  --reload           - Reload configuration after changes (USE THIS for config changes)"
        echo "  --test             - Test configuration syntax before reloading"
        echo "  --status           - Show container and worker status"
        echo "  --doctor           - Run comprehensive health check"
        echo "  --logs [lines]     - Show rspamd logs (default: tail 50 and follow)"
        echo ""
        echo "Configuration Inspection:"
        echo "  --actions          - Show current action thresholds"
        echo "  --headers          - Show milter_headers configuration"
        echo "  --force-actions    - Show force_actions configuration (subject rewrite protection)"
        echo ""
        echo "Container Management:"
        echo "  --start            - Start rspamd and redis containers"
        echo "  --stop             - Stop rspamd and redis containers"
        echo "  --restart          - Restart rspamd (RARELY NEEDED - use --reload instead)"
        echo ""
        echo "Troubleshooting:"
        echo "  --clear-redis      - Clear Redis database and reload config"
        echo "  --shell            - Open shell in rspamd container"
        echo "  --redis-shell      - Open Redis CLI"
        echo ""
        echo "  --help, -h         - Show this help message"
        echo ""
        echo "Note: Commands work with or without '--' prefix"
        echo ""
        echo "=== IMPORTANT WORKFLOW ==="
        echo ""
        echo "After editing configuration files:"
        echo "  1. $0 --test              # Check for syntax errors"
        echo "  2. $0 --reload            # Apply changes (NO restart needed)"
        echo "  3. $0 --doctor            # Verify everything is working"
        echo ""
        echo "When to use --restart:"
        echo "  - Container is crashed or broken"
        echo "  - Changes to docker-compose.yml"
        echo "  - After clearing Redis"
        echo "  - Almost never for config changes (use --reload)"
        echo ""
        echo "Common Commands:"
        echo "  $0 --doctor               # Diagnose issues"
        echo "  $0 --reload               # After config changes"
        echo "  $0 --logs                 # Watch live logs"
        echo "  $0 --force-actions        # Verify subject rewrite protection"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use '$0 --help' to see available commands"
        exit 1
        ;;
esac
