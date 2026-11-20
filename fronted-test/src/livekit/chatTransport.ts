import { createUIMessageStream, type ChatTransport, type UIMessageChunk } from 'ai';
import type { Room } from 'livekit-client';

import type { VoiceUIMessage } from './protocol';

const encoder = new TextEncoder();

export class LiveKitChatTransport implements ChatTransport<VoiceUIMessage> {
  private room: Room | undefined;
  private mode: 'voice' | 'text' = 'voice';

  setRoom(room: Room | undefined): void {
    this.room = room;
  }

  setMode(mode: 'voice' | 'text'): void {
    this.mode = mode;
  }

  async sendMessages(options: {
    trigger: 'submit-message' | 'regenerate-message';
    chatId: string;
    messageId?: string;
    messages: VoiceUIMessage[];
    abortSignal?: AbortSignal;
  }): Promise<ReadableStream<UIMessageChunk>> {
    const latest = options.messages[options.messages.length - 1];
    const text = latest?.parts
      .filter((part): part is { type: 'text'; text: string } => part.type === 'text')
      .map((part) => part.text)
      .join('\n')
      .trim();

    if (this.room && this.mode === 'text' && text) {
      const payload = JSON.stringify({
        type: 'user_text_input',
        chat_id: options.chatId,
        text,
      });
      await this.room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
    }

    // Voice/transcription turns arrive via LiveKit Room streams and update the single
    // AI SDK message store directly; this stream completes immediately without spawning
    // a duplicate client-side LLM request.
    return createUIMessageStream<VoiceUIMessage>({
      execute: ({ writer }) => {
        writer.write({ type: 'finish', finishReason: 'stop' });
      },
    });
  }

  async reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
    return null;
  }
}
