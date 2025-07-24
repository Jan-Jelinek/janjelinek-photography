// 1. Import utilities from `astro:content`
import { defineCollection, z } from 'astro:content';

// 2. Import loader(s)
import { glob, file } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: ['**/post.mdx'], base: 'src/collections' }),
  schema: ({ image }) => z.object({
      sequence: z.number(),
      slug: z.string(),
      title: z.string(),
      cover: image(),
        // state: z.enum(['ongoing', 'complete']),
  }),
});

// 4. Export a single `collections` object to register your collection(s)
export const collections = { posts };