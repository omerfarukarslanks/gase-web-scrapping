FROM node:20-slim

# Install Chromium + fonts needed by Remotion renderer
RUN apt-get update && apt-get install -y \
  chromium \
  fonts-liberation \
  fonts-noto \
  fonts-noto-color-emoji \
  libgbm-dev \
  libasound2 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libdbus-1-3 \
  libexpat1 \
  libfontconfig1 \
  libgcc1 \
  libglib2.0-0 \
  libgtk-3-0 \
  libnspr4 \
  libnss3 \
  libpango-1.0-0 \
  libpangocairo-1.0-0 \
  libstdc++6 \
  libx11-6 \
  libx11-xcb1 \
  libxcb1 \
  libxcomposite1 \
  libxcursor1 \
  libxdamage1 \
  libxext6 \
  libxfixes3 \
  libxi6 \
  libxrandr2 \
  libxrender1 \
  libxss1 \
  libxtst6 \
  ca-certificates \
  wget \
  && rm -rf /var/lib/apt/lists/*

# Tell Remotion / Puppeteer where Chromium is
ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /renderer

# Install renderer dependencies first (cache layer)
COPY package.json ./
RUN npm install --omit=dev

# Copy server source
COPY server.mjs ./

EXPOSE 3001

CMD ["node", "server.mjs"]
