# Failure analysis

Cases where `phase1_ok` is false or `failure_reason` is non-empty:

## cross_duplex_ifc_pdf

- **category**: consistency
- **input**: missing 
- **reason**: No IFC or PDF/raster duplex assets in repository data/ (required cross-input case unresolved).

## cross_clinic_pdf

- **category**: consistency
- **input**: missing 
- **reason**: No PDF/raster clinic plan in data/; only IFC clinic available. PDF cross-input unresolved.

## cross_office_pdf

- **category**: consistency
- **input**: missing 
- **reason**: No PDF office plan in data/; benchmark uses IFC vs synthetic raster as partial proxy only.
