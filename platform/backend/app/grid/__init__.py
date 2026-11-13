"""Real power grid: OSM import (ODbL layer), topology snapshots and the cascade engine.

See docs/en/design/MATTER_FLOW_AND_LOCATIONS.md section 7.1 for the ODbL layer rules:
everything imported from OpenStreetMap lives in the ``odbl`` schema and keeps its licence.
"""

ODBL_SCHEMA = "odbl"
OSM_LICENCE = "ODbL-1.0"
OSM_ATTRIBUTION = "© OpenStreetMap contributors (ODbL); tag mappings after Open Infrastructure Map"
