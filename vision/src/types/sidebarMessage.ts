export enum SidebarCommand {

    CheckBackend = "checkBackend",

    SendChat = "sendChat",

    InitialProjectIndexing = "initialProjectIndexing",

    LoadHistory = "loadHistory"

}

export interface SidebarMessage {

    command: SidebarCommand;

    data?: any;

}