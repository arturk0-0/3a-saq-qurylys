FROM node:24-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=custom_ca \
    if [ -f /run/secrets/custom_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/custom_ca; fi; \
    npm ci
COPY . .
RUN npm run build && chown -R node:node /app
USER node
EXPOSE 5173
CMD ["npm", "run", "dev"]
