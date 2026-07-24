export enum SidebarCommand {

    CheckBackend = "checkBackend",

    SendChat = "sendChat",

    InitialProjectIndexing = "initialProjectIndexing",

    LoadHistory = "loadHistory",

    GetProjectInfo = "getProjectInfo"

}

export interface SidebarMessage {

    command: SidebarCommand;

    data?: any;

}