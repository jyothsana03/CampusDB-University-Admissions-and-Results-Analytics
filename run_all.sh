#!/usr/bin/env bash
# Rebuilds the whole CampusDB project with plain psql. Set PGHOST/PGUSER/PGPASSWORD if needed.
set -euo pipefail
cd "$(dirname "$0")"

python3 python/gen_data.py                                   # data/*.csv, sql/data.sql, mongo/activity_logs.jsonl

dropdb --if-exists campusdb;    createdb campusdb
dropdb --if-exists campusdb_py; createdb campusdb_py
psql -q -v ON_ERROR_STOP=1 -d campusdb -f sql/schema.sql -f sql/data.sql
psql -d campusdb -v ON_ERROR_STOP=1 -f sql/queries.sql > outputs/queries_output.txt

python3 python/build_notebook.py                             # loads CSVs into campusdb_py, runs queries, saves charts
PGDATABASE=campusdb python3 python/export_results_for_mongo.py
python3 python/verify_mongo_pipelines.py                     # pandas replica of the MongoDB pipelines
python3 python/build_slide_assets.py                         # needs graphviz (dot/neato)
python3 python/build_deck.py                                 # needs python-pptx and template/template.pptx
echo "done"
