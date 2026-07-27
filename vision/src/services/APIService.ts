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

            if (!response.ok) {
                return {
                    endpoint: endpoint,
                    connected: false,
                    message: "Error",
                    latency: -1
                };
            };
            console.log(response);

            return {
                endpoint: endpoint,
                connected: true,
                message: "Connected",
                latency: latency
            };

        }
        catch {

            return {
                endpoint: endpoint,
                connected: false,
                message: "Offline", 
                latency: -1
            };

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
        return response.json();
    }

}