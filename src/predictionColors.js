// Keep the familiar basic colors, then extend the palette instead of cycling it.
const namedColors = [
  ['#2e7d32','Green'], ['#d35400','Orange'], ['#7b1fa2','Purple'],
  ['#1565c0','Blue'], ['#c62828','Red'], ['#6d4c41','Brown'],
  ['#fbc02d','Yellow'], ['#00838f','Turquoise'], ['#ad1457','Pink'],
  ['#455a64','Blue grey'], ['#76b900','Lime'], ['#172b75','Navy'],
  ['#ee82ee','Violet'], ['#00bfff','Sky blue'], ['#ff8c69','Coral'],
  ['#b8860b','Gold'], ['#708238','Olive'], ['#40e0b0','Mint'],
  ['#8b0035','Burgundy'], ['#b19cd9','Lavender'],
];
export const multiProfilePalette = namedColors.map(([color]) => color);
const names = new Map(namedColors);
const extendedColors = [...multiProfilePalette];
const hslToHex = (hue, saturation, lightness) => {
  const a = saturation * Math.min(lightness, 1 - lightness);
  return '#' + [0, 8, 4].map(n => {
    const k = (n + hue / 30) % 12;
    const value = lightness - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(255 * value).toString(16).padStart(2, '0');
  }).join('');
};
export const getPredictionProfilePaletteColor = index => {
  while (extendedColors.length <= index) {
    const next = extendedColors.length;
    let attempt = 0;
    let color;
    do {
      color = hslToHex((next * 137.508 + attempt++ * 11.73) % 360,
        0.65 + (next % 3) * 0.1, 0.36 + (next % 4) * 0.1);
    } while (names.has(color));
    extendedColors.push(color);
    names.set(color, `Color ${next + 1} (${color})`);
  }
  return extendedColors[index];
};
export const getPredictionProfileColorName = color => names.get(color) ?? color;
