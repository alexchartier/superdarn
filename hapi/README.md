# SuperDARN Hapi Zenodo Service

This service implements the "inventory + redirect" pattern for SuperDARN
Zenodo-hosted files.

Routes:

- `GET /healthz`
- `GET /zenodo_inventory_north`
- `GET /zenodo_inventory_south`
- `GET /apl_superdarn_data?ver=...&rdr=...&yr=...&mo=...&day=...`

`/apl_superdarn_data` resolves a requested file against the Zenodo records API
and returns a `302` redirect to the matching Zenodo file URL.

If an exact fit netCDF file is not present but a daily zip bundle exists for the
requested day, the endpoint falls back to redirecting to `YYYYMMDD.nc.zip` and
marks that with `X-SuperDARN-Zenodo-Match: daily-zip`.

## Run

```bash
cd hapi
npm install
npm start
```

## Configuration

Environment variables:

- `HAPI_HOST` default `127.0.0.1`
- `HAPI_PORT` default `43100`
- `ZENODO_API_BASE_URL` default `https://zenodo.org`
- `ZENODO_REQUEST_TIMEOUT_MS` default `30000`
- `ZENODO_CACHE_TTL_MS` default `900000`
- `ZENODO_RECORD_PAGE_SIZE` default `25`
- `ZENODO_INVENTORY_NORTH_FILE` default `/project/superdarn/www/config/zenodo_inventory_north.json`
- `ZENODO_INVENTORY_SOUTH_FILE` default `/project/superdarn/www/config/zenodo_inventory_south.json`

## Notes

- `ver=2.5` resolves individual fit netCDF files from older per-file Zenodo
  records.
- `ver=3.0` prefers older per-file `v3.0.despeckled` records when available.
- `ver=V3_grid` resolves individual grid netCDF files.
