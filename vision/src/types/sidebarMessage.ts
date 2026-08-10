export enum SidebarCommand {

    CheckBackend = "checkBackend",

    GetModelsInfo = "getModelsInfo",

    SendChat = "sendChat",

    InitialProjectIndexing = "initialProjectIndexing",

    LoadHistory = "loadHistory",

    GetProjectInfo = "getProjectInfo",

    GetProjectGitInfo = "getProjectGitInfo",

    GetGuideStatus = "getGuideStatus",

    GetProjectList = "getProjectList",

    GenerateProjectBrief = "generateProjectBrief",

    GetProjectBrief = "getProjectBrief",

    GenerateRAGTEST = "generateRAGTEST",

    UpdateEndpoint = "updateEndpoint",

    UpdateModelId = "updateModelId",

    UpdateCommitId = "updateCommitId",

    ToggleGuide = "toggleGuide"
}

export interface SidebarMessage {

    command: SidebarCommand;

    data?: any;

}