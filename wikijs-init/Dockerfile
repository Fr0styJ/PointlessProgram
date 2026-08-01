FROM requarks/wiki:2@sha256:68f0d1848261ae76492ba358e30a96a76fed5d97a3fff381656082bf90f70d7e

COPY --chown=node:node curated-en.json /wiki/server/locales/fakeco-curated-en.json
COPY --chown=node:node install-curated-locale.js /tmp/install-curated-locale.js
RUN node /tmp/install-curated-locale.js \
    && rm /tmp/install-curated-locale.js
