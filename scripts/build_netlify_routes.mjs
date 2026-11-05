// Destination administrée au build, jamais fournie par un demandeur.
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
const raw = process.env.CREDIT_BACKEND_ORIGIN;
if (!raw) throw new Error('CREDIT_BACKEND_ORIGIN doit désigner le backend Render HTTPS');
const origin = new URL(raw);
if (origin.protocol !== 'https:' || !origin.hostname.endsWith('.onrender.com') ||
    origin.username || origin.password || origin.port || origin.pathname !== '/' || origin.search || origin.hash) {
  throw new Error('Origine Render HTTPS seule requise, sans identifiants, chemin ni paramètres');
}
const target = origin.origin;
const routes = [`/api/* ${target}/api/:splat 200!`, `/auth/* ${target}/auth/:splat 200!`, `/health ${target}/health 200!`];
fs.writeFileSync(fileURLToPath(new URL('../frontend/dist/_redirects', import.meta.url)), routes.join('\n') + '\n');
console.log('Passerelle même origine configurée vers', target);
