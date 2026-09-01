import { APIService } from "./APIService";
import {
    ChatRequest_SSE,
    ChatStreamData,
    ChatStreamEventName
} from "../types/chat";

export class ChatService {
    constructor(
        private readonly apiService: APIService
    ) {}

    async sendMessage(
        request: ChatRequest_SSE,
        onEvent: (
            event: ChatStreamEventName,
            data: ChatStreamData
        ) => void | Promise<void>,
        signal?: AbortSignal
    ): Promise<void> {
        await this.apiService.postStream(
            "/v1/chat",
            request,
            async (event, rawData) => {
                if (
                    ![
                        "meta",
                        "stage",
                        "delta",
                        "done",
                        "error"
                    ].includes(event)
                ) {
                    return;
                }

                await onEvent(
                    event as ChatStreamEventName,
                    rawData as unknown as ChatStreamData
                );
            },
            signal
        );
    }
}