// Generate the PWA icons (four signal bars, the strongest in amber) as PNGs with
// no image dependencies: pixels are drawn into a buffer and zlib-encoded.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";

const out = join(dirname(fileURLToPath(import.meta.url)), "../public/icons");
mkdirSync(out, { recursive: true });

const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
const crc32 = (buf) => {
  let c = 0xffffffff;
  for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};
const chunk = (type, data) => {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
};

function png(size, maskable) {
  const px = Buffer.alloc(size * size * 4);
  const set = (x, y, [r, g, b]) => {
    if (x < 0 || y < 0 || x >= size || y >= size) return;
    const i = (y * size + x) * 4;
    px[i] = r; px[i + 1] = g; px[i + 2] = b; px[i + 3] = 255;
  };
  const bg = [14, 59, 67], bar = [228, 238, 240], hot = [242, 169, 59];
  const radius = maskable ? 0 : size * 0.18;
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const dx = Math.max(radius - x, 0, x - (size - 1 - radius));
      const dy = Math.max(radius - y, 0, y - (size - 1 - radius));
      if (dx * dx + dy * dy <= radius * radius || radius === 0) set(x, y, bg);
    }
  const pad = maskable ? size * 0.22 : size * 0.16;
  const inner = size - 2 * pad;
  const bars = 4, gap = inner * 0.06, w = (inner - gap * (bars - 1)) / bars;
  for (let i = 0; i < bars; i++) {
    const h = inner * (0.3 + 0.2 * i);
    const x0 = Math.round(pad + i * (w + gap)), y0 = Math.round(pad + inner - h);
    for (let y = y0; y < pad + inner; y++) for (let x = x0; x < x0 + w; x++) set(x, y, i === bars - 1 ? hot : bar);
  }
  const rows = [];
  for (let y = 0; y < size; y++) rows.push(Buffer.concat([Buffer.from([0]), px.subarray(y * size * 4, (y + 1) * size * 4)]));
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", ihdr), chunk("IDAT", deflateSync(Buffer.concat(rows), { level: 9 })), chunk("IEND", Buffer.alloc(0)),
  ]);
}

for (const [name, size, maskable] of [["icon-192.png", 192, false], ["icon-512.png", 512, false],
  ["maskable-512.png", 512, true], ["apple-touch-icon.png", 180, true], ["favicon-32.png", 32, false]]) {
  writeFileSync(join(out, name), png(size, maskable));
}
console.log("icons written to public/icons");
