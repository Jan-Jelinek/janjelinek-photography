// Public R2 bucket holding the resized photos that `py r2sync` makes.
export const IMAGE_BASE: string = import.meta.env.PUBLIC_IMAGE_BASE || "https://images.jj.photography";

export const publicUrl = (key: string) => `${IMAGE_BASE.replace(/\/$/, "")}/${key}`;
