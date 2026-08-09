FROM node:22-slim

WORKDIR /app

# Dependencies first, so this layer is reused unless the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* values are substituted into the browser bundle during the
# build, not read at runtime - so this must be an ARG here, not an environment
# variable on the compose service. The browser runs on the host machine, not
# inside the compose network, so it reaches the API on the published port
# rather than the container hostname "app".
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
