FROM node:20-alpine AS builder
WORKDIR /app

ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_TELEMETRY_DISABLED=1

COPY package.json ./
COPY tsconfig.json next.config.mjs postcss.config.mjs tailwind.config.ts ./
COPY app ./app
COPY components ./components
COPY lib ./lib

RUN npm install && npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000

RUN addgroup -S nodejs && adduser -S nextjs -G nodejs
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
USER nextjs

EXPOSE 3000
CMD ["node", "server.js"]
