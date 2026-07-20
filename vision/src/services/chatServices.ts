import { APIService } from "./APIService";
import { ChatRequest, ChatResponse } from "../types/chat";

export class ChatService {

    constructor(
        private readonly backendService: APIService
    ) {}

    /**
     * 사용자 메시지를 Backend로 전달
     */
    async sendMessage(
        request: ChatRequest
    ): Promise<ChatResponse> {

        return await this.backendService.post(
            "/v1/chat",
            request
        ) as ChatResponse;

    }

}