from __future__ import annotations

import math
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform

from preprocess import soil_enrichment as soils, soil_rasters as rasters
from ce_pipeline.phase03 import script03
import shared_cache


def description(prop, *, left=-19949750, top=8361000):
    return f'''<wcs:CoverageDescriptions xmlns:wcs="http://www.opengis.net/wcs/2.0" xmlns:gml="http://www.opengis.net/gml/3.2">
      <wcs:CoverageDescription><wcs:CoverageId>{prop}_0-5cm_mean</wcs:CoverageId>
      <gml:Envelope srsName="{rasters.CRS_URL}" />
      <gml:RectifiedGrid><gml:origin><gml:Point><gml:pos>{left+125} {top-125}</gml:pos></gml:Point></gml:origin>
        <gml:offsetVector>250 0</gml:offsetVector><gml:offsetVector>0 -250</gml:offsetVector>
        <gml:GridEnvelope><gml:low>0 0</gml:low><gml:high>159245 58033</gml:high></gml:GridEnvelope>
      </gml:RectifiedGrid></wcs:CoverageDescription></wcs:CoverageDescriptions>'''.encode()


class SoilRasterTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="soil-raster-test-")
        self.root = Path(self.directory.name)
        self.cache = self.root / "soil.json"
        self.config = rasters.RasterConfig(tile_pixels=16)
        self.requests = []
        self.values = {"sand": 700, "silt": 200, "clay": 100}
        self.shift = 0
        self.grid = rasters.parse_coverage_description(description("sand"), "sand")
        self.patches = [
            patch.object(rasters, "resolve_shared_cache_dir", return_value=self.root / "cache"),
            patch.object(shared_cache, "resolve_shared_cache_db_path", return_value=self.root / "cache.sqlite3"),
            patch.object(shared_cache, "_resolve_legacy_soil_cache_path", return_value=self.root / "absent.json"),
            patch.object(rasters, "_download", side_effect=self.download),
            patch.object(soils, "_fetch_soilgrids_payload", side_effect=AssertionError("REST must never run")),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.directory.cleanup)
        for item in reversed(self.patches):
            self.addCleanup(item.stop)

    def download(self, url, destination, timeout, *, max_bytes):
        params = parse_qs(urlparse(url).query)
        prop = Path(params["map"][0]).stem
        self.requests.append((params["REQUEST"][0], prop))
        if params["REQUEST"] == ["DescribeCoverage"]:
            destination.write_bytes(description(prop))
            return
        self.assertEqual(params["COVERAGEID"], [f"{prop}_0-5cm_mean"])
        self.assertNotIn("SCALESIZE", params)
        self.assertNotIn("RESOLUTION", params)
        axes = {}
        for value in params["SUBSET"]:
            match = re.fullmatch(r"([XY])\(([-\d.]+),([-\d.]+)\)", value)
            axes[match[1]] = float(match[2]), float(match[3])
        left, right = axes["X"]
        bottom, top = axes["Y"]
        width, height = round((right-left)/250), round((top-bottom)/250)
        with rasterio.open(destination, "w", driver="GTiff", width=width, height=height,
                           count=1, dtype="int16", transform=from_origin(left+self.shift, top, 250, 250)) as dataset:
            # Deliberately omit CRS/NoData, reproducing the real MapServer response.
            dataset.write(np.full((height, width), self.values[prop], dtype="int16"), 1)

    def point(self, row_delta=0, col_delta=0):
        xs, ys = transform("EPSG:4326", rasters.NATIVE_CRS, [32.5], [1.25])
        row = math.floor((self.grid.top-ys[0])/250)
        col = math.floor((xs[0]-self.grid.left)/250)
        row = row // 16 * 16 + 5 + row_delta
        col = col // 16 * 16 + 5 + col_delta
        lons, lats = transform(rasters.NATIVE_CRS, "EPSG:4326",
                              [self.grid.left+(col+.5)*250], [self.grid.top-(row+.5)*250])
        return {soils.LAT_HEADER: lats[0], soils.LON_HEADER: lons[0], "row_id": f"{row}:{col}"}

    def enrich(self, records, *, config=None):
        self.events = []
        return rasters.enrich_records(records, self.cache, config=config or self.config,
                                      progress_callback=lambda *event: self.events.append(event))

    def test_native_regional_download_reuses_pixels_and_preserves_rows_and_categories(self):
        records = [self.point(), self.point(col_delta=1), self.point(), {"row_id": "missing coordinates"}]
        output, metadata = self.enrich(records)
        expected = soils.build_soil_record(sand_gkg=700, silt_gkg=200, clay_gkg=100, depth_to_bedrock_cm=None, source="soilgrids_wcs")
        self.assertEqual([row["row_id"] for row in output], [row["row_id"] for row in records])
        for actual in output[:3]:
            for key in (soils.SOIL_TEXTURE_HEADER, soils.SOIL_DEPTH_HEADER, "soil_source", "soil_texture_usda_class"):
                self.assertEqual(actual[key], expected[key])
        self.assertEqual(output[-1], records[-1])
        self.assertEqual(Counter(request for request, _ in self.requests), {"DescribeCoverage": 3, "GetCoverage": 3})
        self.assertEqual(metadata["soil_service_queries"], 0)
        self.assertEqual(metadata["soil_raster_valid_cells"], 2)
        self.assertEqual(metadata["soil_depth_default_cells"], 2)
        self.assertEqual(metadata["soil_raster_blocks_read"], 3)
        stages = {event[1] for event in self.events}
        self.assertTrue({"Planning soil raster downloads", "Downloading soil rasters", "Sampling soil raster blocks", "Saving soil raster results"} <= stages)
        self.assertEqual(self.events[-1][3]["stage_percent"], 100)
        for path in (self.root / "cache").rglob("*.tif"):
            with rasterio.open(path) as raster:
                self.assertEqual(raster.crs, rasterio.crs.CRS.from_string(rasters.NATIVE_CRS))

    def test_warm_point_cache_avoids_network_and_raster_opens(self):
        records = [self.point(), self.point(col_delta=1)]
        expected, _ = self.enrich(records)
        with patch.object(rasters, "_download", side_effect=AssertionError("no network")), patch.object(
            rasterio, "open", side_effect=AssertionError("no raster opens"),
        ):
            actual, metadata = self.enrich(records)
        self.assertEqual(actual, expected)
        self.assertEqual(metadata["soil_cache_hits"], 2)
        self.assertEqual(metadata["soil_raster_files_downloaded"], 0)

    def test_partial_point_cache_reuses_existing_regional_files(self):
        self.enrich([self.point()])
        with patch.object(rasters, "_download", side_effect=AssertionError("existing files must be reused")):
            output, metadata = self.enrich([self.point(), self.point(col_delta=1)])
        self.assertEqual(metadata["soil_cache_hits"], 1)
        self.assertEqual(metadata["soil_raster_files_cached"], 3)
        self.assertEqual(metadata["soil_persisted_points"], 1)
        self.assertEqual(output[1]["soil_source"], "soilgrids_wcs")

    def test_revision_invalidates_point_and_file_caches(self):
        self.enrich([self.point()])
        self.requests.clear()
        _, metadata = self.enrich([self.point()], config=rasters.RasterConfig(tile_pixels=16, revision="new-source-version"))
        self.assertEqual(metadata["soil_cache_hits"], 0)
        self.assertEqual(metadata["soil_raster_files_downloaded"], 3)
        self.assertEqual(len(self.requests), 6)

    def test_nodata_is_identified_and_default_texture_is_not_counted_as_real(self):
        self.values["clay"] = -32768
        output, metadata = self.enrich([self.point()])
        self.assertEqual(output[0]["soil_source"], "fallback_default")
        self.assertEqual(metadata["soil_raster_valid_cells"], 0)
        self.assertEqual(metadata["soil_fallback_cells"], 1)
        self.assertEqual(output[0][soils.SOIL_TEXTURE_HEADER], soils.DEFAULT_TEXTURE_BUCKET)

    def test_valid_legacy_depth_is_preserved_and_old_fallback_texture_is_replaced(self):
        point = self.point()
        point_id = soils.cache_key(point[soils.LAT_HEADER], point[soils.LON_HEADER])
        previous = soils.build_soil_record(sand_gkg=None, silt_gkg=None, clay_gkg=None, depth_to_bedrock_cm=50, source="soilgrids")
        shared_cache.upsert_soil_cache_entries({point_id: previous})
        output, metadata = self.enrich([point])
        self.assertEqual(output[0][soils.SOIL_DEPTH_HEADER], "50cm")
        self.assertEqual(metadata["soil_depth_default_cells"], 0)
        self.assertEqual(output[0][soils.SOIL_TEXTURE_HEADER], "Sandy Loam")

    def test_shifted_or_invalid_download_is_not_published_or_converted_to_rest(self):
        self.shift = 250
        with patch.object(rasters.time, "sleep"), self.assertRaisesRegex(RuntimeError, "shifted or resampled"):
            self.enrich([self.point()])
        self.assertEqual(list((self.root / "cache").rglob("*.tif")), [])
        self.assertEqual(list((self.root / "cache").rglob("*.part")), [])

    def test_truncated_cached_raster_is_repaired_before_sampling(self):
        self.enrich([self.point()])
        path = next((self.root / "cache").rglob("sand*.tif"))
        path.write_bytes(b"broken GeoTIFF")
        self.requests.clear()
        output, metadata = self.enrich([self.point(col_delta=1)])
        self.assertEqual(metadata["soil_raster_files_downloaded"], 1)
        self.assertEqual(metadata["soil_raster_files_cached"], 2)
        self.assertEqual(self.requests, [("GetCoverage", "sand")])
        self.assertEqual(output[0]["soil_source"], "soilgrids_wcs")

    def test_unaligned_property_grids_fail_before_get_coverage(self):
        original = rasters.parse_coverage_description
        with patch.object(rasters, "parse_coverage_description", side_effect=lambda raw, prop: (
            rasters.CoverageGrid(self.grid.left+250, self.grid.top, 250, self.grid.width, self.grid.height)
            if prop == "clay" else original(raw, prop)
        )), self.assertRaisesRegex(ValueError, "not aligned"):
            self.enrich([self.point()])
        self.assertTrue(all(request == "DescribeCoverage" for request, _ in self.requests))

    def test_phase03_dispatches_to_raster_provider(self):
        import os
        with patch.dict(os.environ, {"APP_PHASE03_SOIL_PROVIDER": "rasters"}), patch.object(
            rasters, "enrich_records", return_value=([], {"soil_provider": "rasters"}),
        ) as enrich:
            _, metadata = script03.enrich_soils([], self.cache)
        enrich.assert_called_once()
        self.assertEqual(metadata["soil_provider"], "rasters")


if __name__ == "__main__":
    unittest.main()
