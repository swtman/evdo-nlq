# Stage 1 — build the React app
FROM node:20-alpine AS builder

# Enable pnpm via corepack (bundled with Node 20)
RUN corepack enable

WORKDIR /app

# Copy manifests first to layer-cache dependency install
COPY package.json pnpm-lock.yaml ./

# Install all deps (including dev, needed for tsc + vite build)
RUN pnpm install --frozen-lockfile

# Copy source and build
COPY . .
RUN pnpm build

# Stage 2 — serve with nginx
FROM nginx:alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our SSE-safe nginx config
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Copy built assets from Stage 1
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 5173

CMD ["nginx", "-g", "daemon off;"]
