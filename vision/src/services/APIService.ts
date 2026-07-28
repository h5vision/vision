import * as vscode from 'vscode';

export interface BackendStatus {
    endpoint: string;
    connected: boolean;
    message: string;
    latency: number;
}

export class APIService {

    constructor() {}

    async checkHealth(): Promise<BackendStatus> {
        const endpoint = vscode.workspace.getConfiguration().get<string>("vision.endpoint",
            "http://127.0.0.1:5000"
        )!;
        let startime = Date.now();

        try {
            const response = await fetch(`${endpoint}/health`);
            const endtime = Date.now();
            const latency = endtime - startime;
            console.log(response);
            if (!response.ok) {
                return {
                    endpoint: endpoint,
                    connected: false,
                    message: "Backend Server Error",
                    latency: -1
                };
            }
            return {
                endpoint: endpoint,
                connected: true,
                message: "Connected",
                latency: latency
            };
        }
        catch (error) {
            if (error instanceof Error) {
                return {
                    endpoint: endpoint,
                    connected: false,
                    message: error.message.toUpperCase(), 
                    latency: -1
                };
            } else {
                return {
                    endpoint: endpoint,
                    connected: false,
                    message: String(error).toUpperCase(), 
                    latency: -1
                };
            }
        }

    }

    async get(path: string) {
        const endpoint = vscode.workspace.getConfiguration().get<string>("vision.endpoint",
            "http://127.0.0.1:5000"
        )!;
        const response = await fetch(
            `${endpoint}${path}`
        );
        return response.json();
    }

    async post(path: string, body: any) {
        const endpoint = vscode.workspace.getConfiguration().get<string>("vision.endpoint",
            "http://127.0.0.1:5000"
        )!;
        const response = await fetch(
            `${endpoint}${path}`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(body)
            }
        );
        console.log(response);
        return response.json();
    }

}