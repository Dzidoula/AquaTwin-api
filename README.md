# AquaTwin-Drip — Backend mock

API FastAPI minimale pour développer et tester l'app Flutter de bout en bout, **avant** que le vrai moteur AquaTwin-Drip (mémoire, ch. 3 & 6 — solveur de Richards, AquaCrop, Random Forest) soit exposé en HTTP. Ce n'est pas le moteur réel : les recommandations et l'historique sont générés de façon déterministe (pas aléatoire à chaque appel, mais pas scientifiquement valides).

## Lancer le serveur

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Doc interactive : http://localhost:8000/docs

Une base SQLite (`aquatwin_mock.db`) est créée automatiquement à côté — supprimez-la pour repartir de zéro.

## Connexion depuis l'app Flutter

`lib/core/app_config.dart` pointe déjà vers ce serveur local :
- `http://10.0.2.2:8000` sur émulateur Android (alias spécial vers l'hôte).
- `http://localhost:8000` partout ailleurs (iOS simulator, desktop, web).

Sur un téléphone physique, remplacez par l'IP locale de votre machine (ex. `http://192.168.1.x:8000`).

## Connexion (mock)

Pas de vrai SMS envoyé. Le code de vérification est toujours **`1234`**.

Le rôle est déterminé par une convention de test uniquement : un numéro contenant `1111` se connecte en agent de coopérative, tout autre numéro en agriculteur.

## Authentification par session

`POST /auth/otp/verify` retourne un `token` opaque en plus des infos utilisateur. Toutes les routes sous `/fields` et `/cooperative/fields` exigent ce token en en-tête `Authorization: Bearer <token>` :

```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/auth/otp/verify" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+22990000001","code":"1234"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

curl -X POST "http://localhost:8000/fields" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"crop":"tomate","size_hectares":0.5,"latitude":9.3,"longitude":2.6}'
```

Un champ n'est modifiable/consultable que par son propriétaire ou par un agent de coopérative (rôle `agent_cooperative`). `GET /cooperative/fields` est réservé à ce rôle et renvoie les champs de tous les agriculteurs.

Les comptes créés par un agent via `POST /cooperative/farmers` sautent entièrement la vérification OTP, par conception : l'agent est déjà authentifié et de confiance, et peut ne pas avoir le téléphone de l'agriculteur en main pendant la visite.

Si vous aviez déjà une base `aquatwin_mock.db` d'avant cette fonctionnalité, supprimez-la (`rm backend/aquatwin_mock.db`) avant de relancer le serveur — le schéma a changé (colonne `name`).

## Déclenchement automatique quotidien (scheduler)

`app/scheduler.py` lance un calcul du vrai moteur pour chaque champ qui n'en a
pas encore reçu un aujourd'hui — pas de repli mock : `GET .../recommendation`
renvoie 404 et `GET .../history` une liste vide tant qu'aucun calcul réel n'a
abouti pour un champ. Un seul calcul roule à la fois (le moteur ne supporte
pas la concurrence), donc les champs sont traités en série ; l'échec d'un
champ (bug de convergence, ISRIC indisponible...) n'empêche pas les suivants.

Prévu pour tourner une fois par jour via un timer systemd (`deploy/`) : le
moteur avance `jour_julien` de +1 à chaque appel, donc l'appeler plus d'une
fois par jour ferait avancer le cycle de la culture plus vite que la réalité.

```bash
sudo cp deploy/aquatwin-scheduler.service deploy/aquatwin-scheduler.timer /etc/systemd/system/
# Copier les lignes Environment= de aquatwin-api.service dans
# aquatwin-scheduler.service (DATABASE_URL, ENGINE_OCTAVE_CMD, ENGINE_SCRIPT_PATH)
sudo systemctl daemon-reload
sudo systemctl enable --now aquatwin-scheduler.timer
```

Lancer un passage manuellement (test) : `sudo systemctl start aquatwin-scheduler.service`,
puis `journalctl -u aquatwin-scheduler -n 50`.

## Endpoints

| Méthode | Route | Description |
|---|---|---|
| POST | `/auth/otp/request` | Envoi du code (mock, ne fait rien) |
| POST | `/auth/otp/verify` | Vérifie le code, crée/retrouve l'utilisateur, retourne un token |
| POST | `/fields` | Crée un champ pour l'utilisateur authentifié (nécessite `Authorization: Bearer <token>`) |
| PATCH | `/fields/{id}` | Corrige la taille d'un champ (propriétaire ou agent de coopérative) |
| GET | `/fields/{id}/recommendation` | Recommandation du jour (générée, déterministe) |
| GET | `/fields/{id}/history` | 14 derniers jours (eau utilisée, humidité sol) |
| GET | `/cooperative/fields` | Tous les champs des agriculteurs (réservé au rôle `agent_cooperative`) |
| POST | `/cooperative/farmers` | Crée un compte agriculteur sans OTP (réservé à agent_cooperative) |
