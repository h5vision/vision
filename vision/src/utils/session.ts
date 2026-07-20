import { randomUUID } from "crypto";

let sessionId: string | undefined;

export function getSessionId(): string {
    if (!sessionId) {
        sessionId = randomUUID();
    }

    return sessionId;
}

export function resetSessionId(): string {
    sessionId = randomUUID();
    return sessionId;
}