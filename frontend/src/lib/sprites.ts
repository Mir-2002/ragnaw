const SPRITES = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon";

/**
 * The pixel sprite for a Pokémon, from the official-artwork URL the backend sends:
 * Emerald's sprite for #1–386, the default pixel sprite for everything later (and forms).
 */
export function pixelSprite(artworkUrl: string): string | undefined {
  const id = Number(artworkUrl.match(/\/(\d+)\.png$/)?.[1]);
  if (!id) return undefined;
  return id <= 386 ? `${SPRITES}/versions/generation-iii/emerald/${id}.png` : `${SPRITES}/${id}.png`;
}
