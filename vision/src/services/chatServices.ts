import { APIService } from "./APIService";
import { ChatRequest, ChatResponse, ChatMessage } from "../types/chat";
import * as fs from 'fs';

export class ChatService {

    constructor( 
        private readonly APIService: APIService
    ) {};

    /**
     * 사용자 메시지를 Backend로 전달
     */
    async sendMessage(request: ChatRequest): Promise<ChatResponse> {
        return await this.APIService.post(
            "/chat",
            request
        ) as ChatResponse;
    };

};