#!/bin/bash
# Auto-deploy script for Bokföringssystem
# Pulls from GitHub every 10 seconds and rebuilds if needed

REPO_DIR="${HOME}/Development/bok"
API_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"

echo "🚀 Auto-deploy watcher started"
echo "📁 Watching: ${REPO_DIR}"
echo "🌐 API will be available at: ${API_URL}"
echo "🌐 Frontend will be available at: ${FRONTEND_URL}"
echo "⏱️  Checking every 10 seconds..."
echo "================================================"

cd "${REPO_DIR}" || exit 1

# Initial build
echo "📦 Initial build..."
docker compose up --build --detach

# Track last commit
LAST_COMMIT=$(git rev-parse HEAD)
echo "📝 Current commit: ${LAST_COMMIT:0:7}"

while true; do
    sleep 10
    
    # Fetch latest changes
    git fetch origin main --quiet
    
    # Check if there are new commits
    LOCAL_COMMIT=$(git rev-parse HEAD)
    REMOTE_COMMIT=$(git rev-parse origin/main)
    
    if [ "$LOCAL_COMMIT" != "$REMOTE_COMMIT" ]; then
        echo ""
        echo "🔔 New commits detected!"
        echo "   Local:  ${LOCAL_COMMIT:0:7}"
        echo "   Remote: ${REMOTE_COMMIT:0:7}"
        echo ""
        
        # Pull changes
        echo "📥 Pulling changes..."
        git pull origin main
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "🔨 Rebuilding containers..."
            docker compose down
            docker compose up --build --detach
            
            if [ $? -eq 0 ]; then
                echo ""
                echo "✅ Build successful!"
                echo "🧪 Running demo data generator..."
                docker compose run demo-runner
                
                echo ""
                echo "🌐 Services are ready:"
                echo "   API:      ${API_URL}"
                echo "   Frontend: ${FRONTEND_URL}"
                echo ""
            else
                echo "❌ Build failed!"
            fi
        else
            echo "❌ Git pull failed!"
        fi
        
        # Update last commit
        LAST_COMMIT=$(git rev-parse HEAD)
        echo "📝 Now at commit: ${LAST_COMMIT:0:7}"
        echo "================================================"
    fi
done
