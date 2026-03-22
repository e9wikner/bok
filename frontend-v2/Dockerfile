# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Runtime stage
FROM node:20-alpine

WORKDIR /app

# Copy only necessary files from builder
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

ENV NODE_ENV=production
ENV NEXT_PUBLIC_API_URL=http://bokfoering-api:8000
ENV NEXT_PUBLIC_API_KEY=dev-key-change-in-production

EXPOSE 3000

CMD ["node", "server.js"]
