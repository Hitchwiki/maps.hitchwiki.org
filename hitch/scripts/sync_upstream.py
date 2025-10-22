"""Script to fetch and merge upstream hitchmap database dump from hitchwiki.org."""
import gzip
import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import requests

from hitch.extensions import db
from hitch.helpers import get_dirs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Configuration
UPSTREAM_URL = "https://nomadwiki.org/dumps/hitchmap.com-dump.sqlite.gz"
TABLES_TO_SYNC = [
    "points",
    "duplicates", 
    "service_areas",
    "road_islands"
]


def create_backup():
    """Create a timestamped backup of the local database."""
    dirs = get_dirs()
    db_path = dirs["db"]
    backup_dir = os.path.join(db_path, "backups")
    
    # Create backups directory if it doesn't exist
    os.makedirs(backup_dir, exist_ok=True)
    
    # Generate timestamp for backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"points_backup_{timestamp}.sqlite"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    # Copy current database to backup
    local_db_path = os.path.join(db_path, "points.sqlite")
    if os.path.exists(local_db_path):
        shutil.copy2(local_db_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return backup_path
    else:
        logger.warning(f"Local database not found at {local_db_path}")
        return None


def download_upstream_dump():
    """Download and extract the upstream database dump."""
    logger.info(f"Downloading upstream dump from {UPSTREAM_URL}")
    
    try:
        # Download the gzipped file
        response = requests.get(UPSTREAM_URL, timeout=300)  # 5 minute timeout
        response.raise_for_status()
        
        # Create temporary file for the gzipped data
        with tempfile.NamedTemporaryFile(suffix='.sqlite.gz', delete=False) as temp_gz:
            temp_gz.write(response.content)
            temp_gz_path = temp_gz.name
        
        # Extract the gzipped file
        with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as temp_sqlite:
            with gzip.open(temp_gz_path, 'rb') as gz_file:
                shutil.copyfileobj(gz_file, temp_sqlite)
            temp_sqlite_path = temp_sqlite.name
        
        # Clean up the gzipped file
        os.unlink(temp_gz_path)
        
        logger.info(f"Downloaded and extracted upstream dump to {temp_sqlite_path}")
        return temp_sqlite_path
        
    except requests.RequestException as e:
        logger.error(f"Failed to download upstream dump: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to extract upstream dump: {e}")
        raise


def get_table_schema(cursor, table_name):
    """Get the schema for a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return [col[1] for col in columns]  # Return column names


def sync_table(upstream_cursor, local_cursor, table_name):
    """Sync a single table from upstream to local database."""
    logger.info(f"Syncing table: {table_name}")
    
    try:
        # Get table schema
        upstream_columns = get_table_schema(upstream_cursor, table_name)
        local_columns = get_table_schema(local_cursor, table_name)
        
        # Find common columns
        common_columns = [col for col in upstream_columns if col in local_columns]
        if not common_columns:
            logger.warning(f"No common columns found for table {table_name}")
            return
        
        # Get all data from upstream table
        columns_str = ", ".join(common_columns)
        upstream_cursor.execute(f"SELECT {columns_str} FROM {table_name}")
        rows = upstream_cursor.fetchall()
        
        if not rows:
            logger.info(f"No data found in upstream table {table_name}")
            return
        
        # Insert data into local table using INSERT OR IGNORE to avoid conflicts
        placeholders = ", ".join(["?" for _ in common_columns])
        insert_sql = f"INSERT OR IGNORE INTO {table_name} ({columns_str}) VALUES ({placeholders})"
        
        local_cursor.executemany(insert_sql, rows)
        local_cursor.connection.commit()
        
        logger.info(f"Synced {len(rows)} rows from {table_name}")
        
    except Exception as e:
        logger.error(f"Failed to sync table {table_name}: {e}")
        raise


def sync_databases(upstream_db_path, local_db_path):
    """Sync all configured tables from upstream to local database."""
    logger.info("Starting database synchronization")
    
    try:
        # Connect to both databases
        upstream_conn = sqlite3.connect(upstream_db_path)
        local_conn = sqlite3.connect(local_db_path)
        
        upstream_cursor = upstream_conn.cursor()
        local_cursor = local_conn.cursor()
        
        # Get list of tables that exist in upstream database
        upstream_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        upstream_tables = [row[0] for row in upstream_cursor.fetchall()]
        
        # Sync each configured table
        synced_tables = []
        for table_name in TABLES_TO_SYNC:
            if table_name in upstream_tables:
                sync_table(upstream_cursor, local_cursor, table_name)
                synced_tables.append(table_name)
            else:
                logger.warning(f"Table {table_name} not found in upstream database")
        
        logger.info(f"Successfully synced {len(synced_tables)} tables: {synced_tables}")
        
    except Exception as e:
        logger.error(f"Database synchronization failed: {e}")
        raise
    finally:
        # Close database connections
        if 'upstream_conn' in locals():
            upstream_conn.close()
        if 'local_conn' in locals():
            local_conn.close()


def main():
    """Main function to orchestrate the sync process."""
    logger.info("Starting upstream database sync")
    
    dirs = get_dirs()
    local_db_path = os.path.join(dirs["db"], "points.sqlite")
    temp_upstream_path = None
    
    try:
        # Create backup of local database
        backup_path = create_backup()
        
        # Download and extract upstream dump
        temp_upstream_path = download_upstream_dump()
        
        # Sync databases
        sync_databases(temp_upstream_path, local_db_path)
        
        logger.info("Upstream database sync completed successfully")
        
    except Exception as e:
        logger.error(f"Upstream database sync failed: {e}")
        raise
    finally:
        # Clean up temporary files
        if temp_upstream_path and os.path.exists(temp_upstream_path):
            os.unlink(temp_upstream_path)
            logger.info("Cleaned up temporary files")


if __name__ == "__main__":
    main()
