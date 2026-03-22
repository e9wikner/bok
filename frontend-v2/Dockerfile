# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# Runtime stage
FROM node:20-alpine

WORKDIR /app

RUN npm install -g next

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules

ENV NEXT_PUBLIC_API_URL=http://api:8000
ENV NEXT_PUBLIC_API_KEY=dev-key-change-in-production

EXPOSE 3000

CMD ["npm", "run", "start"]
