# Deployment Guide

## Production Environment

- **Backend**: Docker container on VM (`socialflow`)
- **Frontend**: Vercel (auto-deploys on git push)
- **Database**: SQLite in Docker volume

---

## Backend Deployment Steps

### 1. SSH into the VM
```bash
ssh rsumit123@socialflow
```

### 2. Navigate to project directory
```bash
cd ~/willow-leather-api
```

### 3. Pull latest code
```bash
git pull origin main
```

### 4. Database Migrations (if needed)

**Find the database:**
```bash
sudo find / -name "willow_leather.db" 2>/dev/null
```

Database location:
```
/var/lib/docker/volumes/willow-leather-api_willow-data/_data/willow_leather.db
```

**Run migrations:**
```bash
# Example: Adding a new column
sudo sqlite3 /var/lib/docker/volumes/willow-leather-api_willow-data/_data/willow_leather.db "ALTER TABLE table_name ADD COLUMN column_name VARCHAR(20);"
```

**Note:** If you get "duplicate column name" error, the column already exists - that's fine.

### 5. Rebuild and restart Docker container
```bash
cd ~/willow-leather-api
docker-compose down
docker-compose build
docker-compose up -d
```

### 6. Verify deployment
```bash
# Check container is running
docker ps | grep willow

# Check logs for errors
docker logs willow-leather-api --tail 50
```

---

## Useful Commands

### Check running containers
```bash
docker ps
```

### View container logs
```bash
docker logs willow-leather-api --tail 100
docker logs -f willow-leather-api  # follow logs in real-time
```

### Access database directly
```bash
sudo sqlite3 /var/lib/docker/volumes/willow-leather-api_willow-data/_data/willow_leather.db
```

Common SQLite commands:
```sql
.tables                     -- list all tables
.schema table_name          -- show table structure
SELECT * FROM table LIMIT 5; -- query data
.quit                       -- exit
```

### Restart container (without rebuild)
```bash
docker restart willow-leather-api
```

### Stop and remove container
```bash
docker stop willow-leather-api
docker rm willow-leather-api
```

### Check which process is using a port
```bash
sudo lsof -i :8002
```

---

## Troubleshooting

### Container won't start
```bash
# Check logs
docker logs willow-leather-api

# Check if port is in use
sudo lsof -i :8002
```

### Database locked error
```bash
# Restart the container
docker restart willow-leather-api
```

### Find where database is
```bash
sudo find / -name "*.db" 2>/dev/null | grep willow
```

### Check process working directory
```bash
# Get PID from docker ps or ps aux
sudo ls -l /proc/<PID>/cwd
```

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Vercel        │     │   VM (Docker)   │
│   (Frontend)    │────▶│   (Backend)     │
│   Port: 443     │     │   Port: 8002    │
└─────────────────┘     └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │  Docker Volume  │
                        │  (SQLite DB)    │
                        └─────────────────┘
```

---

## Migration History

| Date       | Migration                                           |
|------------|-----------------------------------------------------|
| 2025-01-26 | Added `current_category` to `auctions` table        |
| 2025-01-26 | Added `category` to `auction_player_entries` table  |
