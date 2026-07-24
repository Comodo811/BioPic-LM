"""Tile-validity tracking for the image display cache."""

from __future__ import annotations

from dataclasses import dataclass, field

DisplayRect = tuple[int, int, int, int]
TileCoord = tuple[int, int]


@dataclass(slots=True)
class DisplayTileCache:
    """Track which canvas tiles contain current display pixels.

    This intentionally stores cache state only. The actual pixels stay in the
    drawable/projection buffers and the Qt canvas owns only rendered pixmaps.
    """

    tile_size: int = 256
    valid_tiles: set[TileCoord] = field(default_factory=set)

    def invalidate_full(self) -> None:
        """Mark the complete display cache as invalid."""
        self.valid_tiles.clear()

    def invalidate_area(self, rect: DisplayRect) -> set[TileCoord]:
        """Invalidate and return all tiles intersecting an image-space rect."""
        tiles = self.tiles_for_rect(rect)
        self.valid_tiles.difference_update(tiles)
        return tiles

    def mark_valid(self, tile_x: int, tile_y: int) -> None:
        """Mark one tile as matching the current display buffer."""
        self.valid_tiles.add((int(tile_x), int(tile_y)))

    def is_valid(self, tile_x: int, tile_y: int) -> bool:
        """Return whether a tile is known-current."""
        return (int(tile_x), int(tile_y)) in self.valid_tiles

    def tiles_for_rect(self, rect: DisplayRect) -> set[TileCoord]:
        """Return tile coordinates intersecting an image-space rect."""
        x, y, width, height = rect
        if width <= 0 or height <= 0:
            return set()
        x0 = max(0, int(x)) // self.tile_size
        y0 = max(0, int(y)) // self.tile_size
        x1 = max(0, int(x + width - 1)) // self.tile_size
        y1 = max(0, int(y + height - 1)) // self.tile_size
        return {
            (tile_x, tile_y)
            for tile_y in range(y0, y1 + 1)
            for tile_x in range(x0, x1 + 1)
        }

    def tile_rect(self, tile_x: int, tile_y: int) -> DisplayRect:
        """Return the image-space rect covered by one tile."""
        x = int(tile_x) * self.tile_size
        y = int(tile_y) * self.tile_size
        return (x, y, self.tile_size, self.tile_size)
