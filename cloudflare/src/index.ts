import { Container } from '@cloudflare/containers';
import { SignJWT } from 'jose';

interface Env {
  ASSETS: Fetcher;
  LIVEKIT_AGENT: DurableObjectNamespace;
  LIVEKIT_URL: string;
  LIVEKIT_API_KEY: string;
  LIVEKIT_API_SECRET: string;
  OPENROUTER_API_KEY: string;
  OPENROUTER_MODEL: string;
  STT_MODEL?: string;
  TTS_MODEL?: string;
  TTS_VOICE?: string;
  LANGFUSE_PUBLIC_KEY?: string;
  LANGFUSE_SECRET_KEY?: string;
  LANGFUSE_BASE_URL?: string;
  LANGFUSE_TRACING_ENABLED?: string;
  LANGFUSE_TRACING_ENVIRONMENT?: string;
  LANGFUSE_RELEASE?: string;
  GMAIL_CLIENT_SECRET_JSON_B64?: string;
  GMAIL_TOKEN_JSON_B64?: string;
}

const AGENT_INSTANCE = 'care-support-livekit-agent';
const AGENT_IDLE_TIMEOUT = '15m';
const TOKEN_TTL_SECONDS = 10 * 60;

function configuredEnvironment(env: Env): Record<string, string> {
  const names = [
    'LIVEKIT_URL',
    'LIVEKIT_API_KEY',
    'LIVEKIT_API_SECRET',
    'OPENROUTER_API_KEY',
    'OPENROUTER_MODEL',
    'STT_MODEL',
    'TTS_MODEL',
    'TTS_VOICE',
    'LANGFUSE_PUBLIC_KEY',
    'LANGFUSE_SECRET_KEY',
    'LANGFUSE_BASE_URL',
    'LANGFUSE_TRACING_ENABLED',
    'LANGFUSE_TRACING_ENVIRONMENT',
    'LANGFUSE_RELEASE',
    'GMAIL_CLIENT_SECRET_JSON_B64',
    'GMAIL_TOKEN_JSON_B64',
  ] as const;

  return Object.fromEntries(
    names.flatMap((name) => {
      const value = env[name];
      return typeof value === 'string' && value.trim() ? [[name, value]] : [];
    }),
  );
}

function missingRuntimeConfiguration(env: Env): string[] {
  return ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'OPENROUTER_API_KEY', 'OPENROUTER_MODEL']
    .filter((name) => {
      const value = env[name as keyof Env];
      return typeof value !== 'string' || !value.trim();
    });
}

async function issueToken(env: Env): Promise<{ participant_token: string; server_url: string }> {
  const missing = missingRuntimeConfiguration(env);
  if (missing.length) {
    throw new Error(`Missing runtime configuration: ${missing.join(', ')}`);
  }
  if (!env.LIVEKIT_URL.startsWith('wss://')) {
    throw new Error('LIVEKIT_URL must use wss:// in the public deployment');
  }

  const room = `frontend-${crypto.randomUUID().replaceAll('-', '')}`;
  const identity = `browser-${crypto.randomUUID().replaceAll('-', '')}`;
  const secret = new TextEncoder().encode(env.LIVEKIT_API_SECRET);
  const participant_token = await new SignJWT({
    video: {
      room,
      roomJoin: true,
      canPublish: true,
      canSubscribe: true,
      canPublishData: false,
      canPublishSources: ['microphone'],
    },
  })
    .setProtectedHeader({ alg: 'HS256', typ: 'JWT' })
    .setIssuer(env.LIVEKIT_API_KEY)
    .setSubject(identity)
    .setJti(crypto.randomUUID())
    .setIssuedAt()
    .setExpirationTime(`${TOKEN_TTL_SECONDS}s`)
    .sign(secret);

  return { participant_token, server_url: env.LIVEKIT_URL };
}

async function ensureAgentIsRunning(env: Env): Promise<void> {
  const response = await env.LIVEKIT_AGENT
    .getByName(AGENT_INSTANCE)
    .fetch('https://agent.internal/health');
  if (!response.ok) {
    throw new Error(`LiveKit agent health check failed (${response.status})`);
  }
}

/** Runs the Linux container that maintains the outbound LiveKit agent connection. */
export class LiveKitAgent extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = AGENT_IDLE_TIMEOUT;
  enableInternet = true;

  constructor(ctx: DurableObjectState<Env>, env: Env) {
    super(ctx, env);
    this.envVars = configuredEnvironment(env);
  }

  override async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/health') {
      return new Response('Not found', { status: 404 });
    }
    return this.containerFetch(request);
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/api/token') {
      if (request.method !== 'POST') {
        return new Response('Method not allowed', { status: 405, headers: { Allow: 'POST' } });
      }
      const origin = request.headers.get('Origin');
      if (origin && origin !== url.origin) {
        return new Response('Forbidden origin', { status: 403 });
      }

      try {
        // Starting before issuing a room token reduces the first-call delay and
        // makes the agent available before the browser participant joins.
        await ensureAgentIsRunning(env);
        const token = await issueToken(env);
        return Response.json(token, { headers: { 'Cache-Control': 'no-store' } });
      } catch (error) {
        console.error('Unable to create LiveKit token or start agent', error);
        return Response.json({ error: 'Voice service is temporarily unavailable' }, { status: 503 });
      }
    }

    if (url.pathname.startsWith('/api/')) {
      return new Response('Not found', { status: 404 });
    }
    return env.ASSETS.fetch(request);
  },

  scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): void {
    // Containers sleep when idle. A short, internal health probe keeps the
    // long-lived agent connected to LiveKit without exposing a public endpoint.
    ctx.waitUntil(ensureAgentIsRunning(env));
  },
} satisfies ExportedHandler<Env>;
