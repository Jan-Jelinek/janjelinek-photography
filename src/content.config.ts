import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';
import { asideOf } from './lib/asides';

const caption = z.object({
  text: z.string().optional(),
  exposure: z.string().optional(),
});

// A row is either a list of photo file names or a block of text.
// A nested list in a row stacks those photos into one column: ["A", ["B", "C"]].
// `text-r:` instead of `text:` puts the text on the right, right-aligned; `text-f:` uses the full width.
// Like asides, a text section can be a list mixing text and snapshot images (their own small lightbox).
// A string with no spaces ending in a photo extension is an image, in .mp4/.mov/.m4v a video (tap to play);
// anything else is text (one paragraph each).
const textItems = z.union([z.string(), z.array(z.string()).min(1)]);
const row = z.union([
  z.array(z.union([z.string(), z.array(z.string()).min(2)])).min(1),
  z.object({ text: textItems }),
  z.object({ 'text-r': textItems }),
  z.object({ 'text-f': textItems }),
  // An aside beside the photo row right above it: `- aside: ["story…", "Snapchat-1.jpg", ...]`.
  // Its number badge goes on the row's top-right photo; `aside-3:` puts it on the row's 3rd photo
  // instead (counted in reading order, stacks included: in [A, [B, C, D]], A = 1, D = 4).
  z.object({ aside: textItems }),
  z
    .record(z.string().regex(/^aside-[1-9]\d*$/, 'expected `aside` or `aside-<photo number>`'), textItems)
    .refine((r) => Object.keys(r).length === 1, 'one `aside-N` per row'),
]);

// The home page thumbnail: a photo from rows, cropped to a square. `zoom` 1 = the biggest square that
// fits; `x`/`y` (0–100) = the point of the photo at the square's centre.
const cover = z
  .union([
    z.string(),
    z.object({
      photo: z.string(),
      zoom: z.number().min(1).default(1),
      x: z.number().min(0).max(100).default(50),
      y: z.number().min(0).max(100).default(50),
    }),
  ])
  .transform((c) => (typeof c === 'string' ? { photo: c, zoom: 1, x: 50, y: 50 } : c));

const posts = defineCollection({
  loader: glob({ pattern: ['**/post.mdx'], base: 'src/collections' }),
  schema: z.object({
      sequence: z.number(),
      slug: z.string(),
      title: z.string(),
      cover,
      place: z.string().optional(),
      rows: z.array(row).min(1),
      // nullish: a `captions:` key with only comments under it parses as null.
      captions: z.record(z.string(), caption).nullish().transform((c) => c ?? {}),
      // Old format (asides keyed by photo, top level); asides now go inline in rows as `- aside:`. Only kept to point that out.
      commentary: z.unknown().optional(),
      // Photos from rows the home page hero may show (picked at random on each visit).
      feature: z.array(z.string()).min(1).optional(),
      // Dev only: while any post has `feature-test:`, the hero shows only those photos (to try them out).
      // The build ignores it (with a warning), so a leftover one can't take over the live site.
      'feature-test': z.array(z.string()).min(1).optional(),
      // Show each photo's aperture · shutter · ISO under it (from the camera data). A caption's own
      // `exposure` still wins.
      'auto-captions': z.boolean().default(false),
  }).superRefine((data, ctx) => {
      const ids = new Set(
        data.rows.flatMap((r) => (Array.isArray(r) ? r.flat() : [])),
      );
      for (const key of Object.keys(data.captions)) {
        if (!ids.has(key)) {
          ctx.addIssue({
            code: 'custom',
            path: ['captions', key],
            message: `Caption for "${key}", but no photo with that ID is in rows`,
          });
        }
      }
      if (data.commentary != null) {
        ctx.addIssue({
          code: 'custom',
          path: ['commentary'],
          message: 'Asides now go in rows: put `- aside: [...]` right after the photo row it belongs to',
        });
      }
      // An aside row needs a photo row above it (other aside rows in between are fine), and an
      // `aside-N` needs that row to have an Nth photo.
      let photosAbove = 0; // photos in the row above; 0 = not after a photo row
      data.rows.forEach((r, i) => {
        const aside = asideOf(r);
        if (Array.isArray(r)) photosAbove = r.flat().length;
        else if (aside) {
          if (!photosAbove) {
            ctx.addIssue({
              code: 'custom',
              path: ['rows', i],
              message: '`aside` must come right after a photo row (it sits beside that row)',
            });
          } else if (aside.target && aside.target > photosAbove) {
            ctx.addIssue({
              code: 'custom',
              path: ['rows', i],
              message: `\`aside-${aside.target}\`, but the photo row above has only ${photosAbove} photo${photosAbove === 1 ? '' : 's'}`,
            });
          }
        } else photosAbove = 0;
      });
      if (!ids.has(data.cover.photo)) {
        ctx.addIssue({
          code: 'custom',
          path: ['cover'],
          message: `Cover "${data.cover.photo}" isn't a photo in rows`,
        });
      }
      for (const key of ['feature', 'feature-test'] as const) {
        (data[key] ?? []).forEach((name, i) => {
          if (!ids.has(name)) {
            ctx.addIssue({
              code: 'custom',
              path: [key, i],
              message: `Feature "${name}" isn't a photo in rows`,
            });
          }
        });
      }
  }),
});

export const collections = { posts };
