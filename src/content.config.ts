import { defineCollection, z } from 'astro:content';
import { glob, file } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: ['**/post.mdx'], base: 'src/collections' }),
  schema: ({ image }) => z.object({
      sequence: z.number(),
      slug: z.string(),
      title: z.string(),
      cover: image(),
      color: z.string(),
      rotate: z.number(),
  }),
});

export const collections = { posts };