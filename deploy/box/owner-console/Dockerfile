FROM oven/bun:1.4.2-alpine
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production
COPY src ./src
ENV PORT=8890
EXPOSE 8890
USER bun
CMD ["bun", "run", "src/server.ts"]
