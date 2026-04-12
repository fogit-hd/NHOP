# Generates Workflows/AIPresenter/*.xaml from AIInteractivePresenter (run once / when merging).
from pathlib import Path

ROOT = Path(r"c:\Users\Admin\Documents\UiPath\NHOP Project")
SRC = ROOT / "AIInteractivePresenter.xaml"
OUT_DIR = ROOT / "Workflows" / "AIPresenter"
SCRIPTS = Path(__file__).resolve().parent

HEADER = '''<Activity mc:Ignorable="sap sap2010" x:Class="{cls}" xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:s="clr-namespace:System;assembly=System.Private.CoreLib" xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation" xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation" xmlns:scg="clr-namespace:System.Collections.Generic;assembly=System.Private.CoreLib" xmlns:sco="clr-namespace:System.Collections.ObjectModel;assembly=System.Private.CoreLib" xmlns:ui="http://schemas.uipath.com/workflow/activities" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <x:Members>
{members}
  </x:Members>
  <sap2010:WorkflowViewState.IdRef>ActivityBuilder_1</sap2010:WorkflowViewState.IdRef>
  <TextExpression.NamespacesForImplementation>
    <sco:Collection x:TypeArguments="x:String">
      <x:String>GlobalConstantsNamespace</x:String>
      <x:String>GlobalVariablesNamespace</x:String>
      <x:String>System</x:String>
      <x:String>System.Collections.Generic</x:String>
      <x:String>System.Collections.ObjectModel</x:String>
      <x:String>System.Linq</x:String>
      <x:String>Microsoft.VisualBasic</x:String>
      <x:String>UiPath.Core</x:String>
      <x:String>UiPath.Core.Activities</x:String>
    </sco:Collection>
  </TextExpression.NamespacesForImplementation>
  <TextExpression.ReferencesForImplementation>
    <sco:Collection x:TypeArguments="AssemblyReference">
      <AssemblyReference>System.ComponentModel.TypeConverter</AssemblyReference>
      <AssemblyReference>System.Linq</AssemblyReference>
      <AssemblyReference>System.ObjectModel</AssemblyReference>
      <AssemblyReference>Microsoft.VisualBasic</AssemblyReference>
      <AssemblyReference>UiPath.System.Activities</AssemblyReference>
      <AssemblyReference>UiPath.UiAutomation.Activities</AssemblyReference>
    </sco:Collection>
  </TextExpression.ReferencesForImplementation>
{body}
</Activity>
'''

def lines_of(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines(keepends=True)

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not SRC.exists():
        print("Skip: source not found:", SRC)
        return
    monolithic = SRC.read_text(encoding="utf-8")
    # Orchestrator main has no inline Init (Assign_SettingsPath). Keep a monolithic .xaml backup to re-run extraction.
    if "Assign_SettingsPath" not in monolithic:
        print("Skip extraction: SRC has no inline Init block (orchestrator?). Use a monolithic backup as SRC to regenerate Workflows/AIPresenter/*.xaml")
        return
    lines = monolithic.splitlines(keepends=True)

    # --- Init: inner content lines 95-360 (1-based), indices 94:360
    init_inner = "".join(lines[94:360])
    init_members = "\n".join(
        [
            '    <x:Property Name="str_OpenAIKey" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_ElevenLabsKey" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_VoiceId" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_MicrophoneName" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="bln_UseWindowsDefaultMic" Type="InOutArgument(x:Boolean)" />',
            '    <x:Property Name="str_ResolveMicScriptPath" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_ResolvedMicFile" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_OpenDefaultAppScript" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_PlayResponseAudioScript" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_PlayVideoScript" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_SlidesFromCsvScript" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_SlidesIterateTsv" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_PipelineScript" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_NarrationAudioPath" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_FfmpegPath" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_WavInputPath" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_AudioPath" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_SlideVideoPath" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_SlidePrompt" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="dict_Headers" Type="InOutArgument(scg:Dictionary(x:String, x:String))" />',
            '    <x:Property Name="int_SlidesCsvShellResult" Type="InOutArgument(x:Int32)" />',
            '    <x:Property Name="int_PipelineShellResult" Type="InOutArgument(x:Int32)" />',
            '    <x:Property Name="str_GlobalSlideContext" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_GptComposedSlides" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_PythonExe" Type="InOutArgument(x:String)" />',
        ]
    )
    init_body = f'''  <Sequence DisplayName="Init and prepare data" sap:VirtualizedContainerService.HintSize="800,200" sap2010:WorkflowViewState.IdRef="Sequence_InitPrepare">
    <Sequence.Variables>
      <Variable x:TypeArguments="x:String" Name="str_SettingsPath" />
      <Variable x:TypeArguments="x:String" Name="str_SettingsJson" />
    </Sequence.Variables>
{init_inner}  </Sequence>'''
    (OUT_DIR / "AIPresenter_InitAndPrepare.xaml").write_text(
        HEADER.format(cls="AIPresenter_InitAndPrepare", members=init_members, body=init_body),
        encoding="utf-8",
        newline="\n",
    )

    # --- Slide iteration: lines 374-500 (1-based) -> indices 373:500
    slide_inner = "".join(lines[373:500])
    slide_members = "\n".join(
        [
            '    <x:Property Name="slideItem" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_GptComposedSlides" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_GlobalSlideContext" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_OpenDefaultAppScript" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_PythonExe" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_ElevenLabsKey" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_VoiceId" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_FfmpegPath" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_PlayResponseAudioScript" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_NarrationAudioPath" Type="InArgument(x:String)" />',
            '    <x:Property Name="int_QaSlideOrdinal" Type="InOutArgument(x:Int32)" />',
            '    <x:Property Name="dict_Headers" Type="InOutArgument(scg:Dictionary(x:String, x:String))" />',
            '    <x:Property Name="str_ElevenResponseRaw" Type="InOutArgument(x:String)" />',
        ]
    )
    slide_locals = """    <Sequence.Variables>
      <Variable x:TypeArguments="x:String" Name="str_CurrentSlideTitle" />
      <Variable x:TypeArguments="x:String" Name="str_AbsSlideImagePath" />
      <Variable x:TypeArguments="x:String" Name="str_RelSlidePath" />
      <Variable x:TypeArguments="x:String" Name="str_SlideNarrationText" />
      <Variable x:TypeArguments="x:String" Name="str_CurrentSlideContent" />
      <Variable x:TypeArguments="x:String" Name="str_ElevenJsonBody" />
      <Variable x:TypeArguments="x:Int32" Name="int_PlayResponseShellResult" />
    </Sequence.Variables>
"""
    slide_body = f'''  <Sequence DisplayName="Slide iteration" sap:VirtualizedContainerService.HintSize="800,200" sap2010:WorkflowViewState.IdRef="Sequence_SlideIter">
{slide_locals}{slide_inner}  </Sequence>'''
    (OUT_DIR / "AIPresenter_SlideIteration.xaml").write_text(
        HEADER.format(cls="AIPresenter_SlideIteration", members=slide_members, body=slide_body),
        encoding="utf-8",
        newline="\n",
    )

    # --- QA: lines 529-765 (Sequence_QABranch) indices 528:765 — saved as fragment only (no separate .xaml workflow).
    qa_inner = "".join(lines[528:765])
    # Q&A branch XML for inlining into After (and for apply_session_dictionary_args.py); no separate workflow (ST-DBP-002).
    (SCRIPTS / "_qa_inline_fragment.xml").write_text(qa_inner, encoding="utf-8", newline="\n")

    # --- After presentation: lines 505-527 + inline QA + close If + Sequence
    # Lines 505-528: After slides Sequence through <If.Then> of UserWantsQA (stop before Q&A inner Sequence)
    after_head = "".join(lines[504:528])
    # Close If_UserWantsQA and After slides Sequence (lines 766-768)
    after_foot = "".join(lines[765:768])

    after_pres_body = after_head + qa_inner + after_foot
    after_members = "\n".join(
        [
            '    <x:Property Name="str_SlideVideoPath" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_GptComposedSlides" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_PythonExe" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_PlayVideoScript" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_FfmpegPath" Type="InArgument(x:String)" />',
            '    <x:Property Name="str_UserQuestionChoice" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_CurrentSlideContent" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="int_PlaySlideVideoShellResult" Type="InOutArgument(x:Int32)" />',
            '    <x:Property Name="bln_UseWindowsDefaultMic" Type="InOutArgument(x:Boolean)" />',
            '    <x:Property Name="str_ResolveMicScriptPath" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_ResolvedMicFile" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_MicrophoneName" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_RecordInputArgs" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_FfmpegArgLine" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_FfmpegRecordExeFile" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_FfmpegRecordArgFile" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_FfmpegRecordPidFile" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_StartFfmpegScript" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_StopFfmpegScript" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_WavInputPath" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_WhisperJsonBody" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_WhisperResponse" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_OpenAIKey" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_GptUserContent" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_GptJsonBody" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_AIResponse" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_SlidePrompt" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="dict_Headers" Type="InOutArgument(scg:Dictionary(x:String, x:String))" />',
            '    <x:Property Name="str_ElevenJsonBody" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_ElevenResponseRaw" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_AudioPath" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="int_PlayResponseShellResult" Type="InOutArgument(x:Int32)" />',
            '    <x:Property Name="str_PlayResponseAudioScript" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_ElevenLabsKey" Type="InOutArgument(x:String)" />',
            '    <x:Property Name="str_VoiceId" Type="InOutArgument(x:String)" />',
        ]
    )
    (OUT_DIR / "AIPresenter_AfterPresentation.xaml").write_text(
        HEADER.format(cls="AIPresenter_AfterPresentation", members=after_members, body="  " + after_pres_body.strip() + "\n"),
        encoding="utf-8",
        newline="\n",
    )

    print("Written:", OUT_DIR / "AIPresenter_InitAndPrepare.xaml")
    print("Written:", OUT_DIR / "AIPresenter_SlideIteration.xaml")
    print("Written:", SCRIPTS / "_qa_inline_fragment.xml")
    print("Written:", OUT_DIR / "AIPresenter_AfterPresentation.xaml")
    print("Then run: py apply_session_dictionary_args.py  (session dict args, ST-DBP-002)")

    write_main_orchestrator()


def _io(tag: str, key: str, typ: str) -> str:
    return f'            <{tag} x:TypeArguments="{typ}" x:Key="{key}">[{key}]</{tag}>'


def write_main_orchestrator():
    main_path = ROOT / "AIInteractivePresenter.xaml"
    init_args = [
        ("InOutArgument", "str_OpenAIKey", "x:String"),
        ("InOutArgument", "str_ElevenLabsKey", "x:String"),
        ("InOutArgument", "str_VoiceId", "x:String"),
        ("InOutArgument", "str_MicrophoneName", "x:String"),
        ("InOutArgument", "bln_UseWindowsDefaultMic", "x:Boolean"),
        ("InOutArgument", "str_ResolveMicScriptPath", "x:String"),
        ("InOutArgument", "str_ResolvedMicFile", "x:String"),
        ("InOutArgument", "str_OpenDefaultAppScript", "x:String"),
        ("InOutArgument", "str_PlayResponseAudioScript", "x:String"),
        ("InOutArgument", "str_PlayVideoScript", "x:String"),
        ("InOutArgument", "str_SlidesFromCsvScript", "x:String"),
        ("InOutArgument", "str_SlidesIterateTsv", "x:String"),
        ("InOutArgument", "str_PipelineScript", "x:String"),
        ("InOutArgument", "str_NarrationAudioPath", "x:String"),
        ("InOutArgument", "str_FfmpegPath", "x:String"),
        ("InOutArgument", "str_WavInputPath", "x:String"),
        ("InOutArgument", "str_AudioPath", "x:String"),
        ("InOutArgument", "str_SlideVideoPath", "x:String"),
        ("InOutArgument", "str_SlidePrompt", "x:String"),
        ("InOutArgument", "dict_Headers", "scg:Dictionary(x:String, x:String)"),
        ("InOutArgument", "int_SlidesCsvShellResult", "x:Int32"),
        ("InOutArgument", "int_PipelineShellResult", "x:Int32"),
        ("InOutArgument", "str_GlobalSlideContext", "x:String"),
        ("InOutArgument", "str_GptComposedSlides", "x:String"),
        ("InOutArgument", "str_PythonExe", "x:String"),
    ]
    init_xml = "\n".join(_io(t, k, ty) for t, k, ty in init_args)

    slide_in = [
        ("InArgument", "slideItem", "x:String"),
        ("InArgument", "str_GptComposedSlides", "x:String"),
        ("InArgument", "str_GlobalSlideContext", "x:String"),
        ("InArgument", "str_OpenDefaultAppScript", "x:String"),
        ("InArgument", "str_PythonExe", "x:String"),
        ("InArgument", "str_ElevenLabsKey", "x:String"),
        ("InArgument", "str_VoiceId", "x:String"),
        ("InArgument", "str_FfmpegPath", "x:String"),
        ("InArgument", "str_PlayResponseAudioScript", "x:String"),
        ("InArgument", "str_NarrationAudioPath", "x:String"),
    ]
    slide_io = [
        ("InOutArgument", "int_QaSlideOrdinal", "x:Int32"),
        ("InOutArgument", "dict_Headers", "scg:Dictionary(x:String, x:String)"),
        ("InOutArgument", "str_ElevenResponseRaw", "x:String"),
    ]
    slide_xml = "\n".join(_io(t, k, ty) for t, k, ty in slide_in + slide_io)

    after_in = [
        ("InArgument", "str_SlideVideoPath", "x:String"),
        ("InArgument", "str_GptComposedSlides", "x:String"),
        ("InArgument", "str_PythonExe", "x:String"),
        ("InArgument", "str_PlayVideoScript", "x:String"),
        ("InArgument", "str_FfmpegPath", "x:String"),
    ]
    after_io_keys = [
        ("InOutArgument", "str_UserQuestionChoice", "x:String"),
        ("InOutArgument", "str_CurrentSlideContent", "x:String"),
        ("InOutArgument", "int_PlaySlideVideoShellResult", "x:Int32"),
        ("InOutArgument", "bln_UseWindowsDefaultMic", "x:Boolean"),
        ("InOutArgument", "str_ResolveMicScriptPath", "x:String"),
        ("InOutArgument", "str_ResolvedMicFile", "x:String"),
        ("InOutArgument", "str_MicrophoneName", "x:String"),
        ("InOutArgument", "str_RecordInputArgs", "x:String"),
        ("InOutArgument", "str_FfmpegArgLine", "x:String"),
        ("InOutArgument", "str_FfmpegRecordExeFile", "x:String"),
        ("InOutArgument", "str_FfmpegRecordArgFile", "x:String"),
        ("InOutArgument", "str_FfmpegRecordPidFile", "x:String"),
        ("InOutArgument", "str_StartFfmpegScript", "x:String"),
        ("InOutArgument", "str_StopFfmpegScript", "x:String"),
        ("InOutArgument", "str_WavInputPath", "x:String"),
        ("InOutArgument", "str_WhisperJsonBody", "x:String"),
        ("InOutArgument", "str_WhisperResponse", "x:String"),
        ("InOutArgument", "str_OpenAIKey", "x:String"),
        ("InOutArgument", "str_GptUserContent", "x:String"),
        ("InOutArgument", "str_GptJsonBody", "x:String"),
        ("InOutArgument", "str_AIResponse", "x:String"),
        ("InOutArgument", "str_SlidePrompt", "x:String"),
        ("InOutArgument", "dict_Headers", "scg:Dictionary(x:String, x:String)"),
        ("InOutArgument", "str_ElevenJsonBody", "x:String"),
        ("InOutArgument", "str_ElevenResponseRaw", "x:String"),
        ("InOutArgument", "str_AudioPath", "x:String"),
        ("InOutArgument", "int_PlayResponseShellResult", "x:Int32"),
        ("InOutArgument", "str_PlayResponseAudioScript", "x:String"),
        ("InOutArgument", "str_ElevenLabsKey", "x:String"),
        ("InOutArgument", "str_VoiceId", "x:String"),
    ]
    after_xml = "\n".join(_io(t, k, ty) for t, k, ty in after_in + after_io_keys)

    variables_block = """    <Sequence.Variables>
      <Variable x:TypeArguments="x:String" Name="str_SpeechText" />
      <Variable x:TypeArguments="x:String" Name="str_AIResponse" />
      <Variable x:TypeArguments="x:String" Default="Data\\AIPresenter\\Temp\\response.wav" Name="str_AudioPath" />
      <Variable x:TypeArguments="scg:Dictionary(x:String, x:String)" Name="dict_Headers" />
      <Variable x:TypeArguments="x:String" Default="YOUR_OPENAI_API_KEY" Name="str_OpenAIKey" />
      <Variable x:TypeArguments="x:String" Default="YOUR_ELEVENLABS_API_KEY" Name="str_ElevenLabsKey" />
      <Variable x:TypeArguments="x:String" Default="YOUR_VOICE_ID" Name="str_VoiceId" />
      <Variable x:TypeArguments="x:String" Default="Microphone Name" Name="str_MicrophoneName" />
      <Variable x:TypeArguments="x:String" Default="ffmpeg" Name="str_FfmpegPath" />
      <Variable x:TypeArguments="x:String" Name="str_CurrentSlideContent" />
      <Variable x:TypeArguments="x:String" Name="str_SlideVideoPath" />
      <Variable x:TypeArguments="x:String" Name="str_WhisperJsonBody" />
      <Variable x:TypeArguments="x:String" Name="str_GptJsonBody" />
      <Variable x:TypeArguments="x:String" Name="str_ElevenJsonBody" />
      <Variable x:TypeArguments="x:String" Name="str_WhisperResponse" />
      <Variable x:TypeArguments="x:String" Name="str_GptResponseRaw" />
      <Variable x:TypeArguments="x:String" Name="str_ElevenResponseRaw" />
      <Variable x:TypeArguments="x:String" Default="Data\\AIPresenter\\Temp\\output.wav" Name="str_WavInputPath" />
      <Variable x:TypeArguments="x:String" Name="str_RecordInputArgs" />
      <Variable x:TypeArguments="x:String" Name="str_FfmpegArgLine" />
      <Variable x:TypeArguments="x:String" Name="str_FfmpegRecordExeFile" />
      <Variable x:TypeArguments="x:String" Name="str_FfmpegRecordArgFile" />
      <Variable x:TypeArguments="x:String" Name="str_FfmpegRecordPidFile" />
      <Variable x:TypeArguments="x:String" Name="str_StartFfmpegScript" />
      <Variable x:TypeArguments="x:String" Name="str_StopFfmpegScript" />
      <Variable x:TypeArguments="x:String" Name="str_SlidePrompt" />
      <Variable x:TypeArguments="x:String" Name="str_GptUserContent" />
      <Variable x:TypeArguments="x:String" Name="str_UserQuestionChoice" />
      <Variable x:TypeArguments="x:String" Name="str_ResolveMicScriptPath" />
      <Variable x:TypeArguments="x:String" Name="str_ResolvedMicFile" />
      <Variable x:TypeArguments="x:String" Name="str_OpenDefaultAppScript" />
      <Variable x:TypeArguments="x:String" Name="str_PlayResponseAudioScript" />
      <Variable x:TypeArguments="x:String" Name="str_PlayVideoScript" />
      <Variable x:TypeArguments="x:String" Default="pyw" Name="str_PythonExe" />
      <Variable x:TypeArguments="x:Int32" Name="int_PlayResponseShellResult" />
      <Variable x:TypeArguments="x:Int32" Name="int_PlaySlideVideoShellResult" />
      <Variable x:TypeArguments="x:String" Name="str_GlobalSlideContext" />
      <Variable x:TypeArguments="x:String" Name="str_SlidesFromCsvScript" />
      <Variable x:TypeArguments="x:String" Name="str_SlidesIterateTsv" />
      <Variable x:TypeArguments="x:Int32" Name="int_SlidesCsvShellResult" />
      <Variable x:TypeArguments="x:Int32" Name="int_PipelineShellResult" />
      <Variable x:TypeArguments="x:String" Name="str_PipelineScript" />
      <Variable x:TypeArguments="x:String" Name="str_SlideNarrationText" />
      <Variable x:TypeArguments="x:String" Name="str_GptComposedSlides" />
      <Variable x:TypeArguments="x:String" Name="str_NarrationAudioPath" />
      <Variable x:TypeArguments="x:String" Name="str_CurrentSlideTitle" />
      <Variable x:TypeArguments="x:String" Name="str_RelSlidePath" />
      <Variable x:TypeArguments="x:String" Name="str_AbsSlideImagePath" />
      <Variable x:TypeArguments="x:Int32" Default="-1" Name="int_QaSlideOrdinal" />
      <Variable x:TypeArguments="x:Boolean" Default="False" Name="bln_UseWindowsDefaultMic" />
    </Sequence.Variables>"""

    main = f'''<Activity mc:Ignorable="sap sap2010" x:Class="AIInteractivePresenter" xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:s="clr-namespace:System;assembly=System.Private.CoreLib" xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation" xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation" xmlns:scg="clr-namespace:System.Collections.Generic;assembly=System.Private.CoreLib" xmlns:sco="clr-namespace:System.Collections.ObjectModel;assembly=System.Private.CoreLib" xmlns:ui="http://schemas.uipath.com/workflow/activities" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <x:Members>
    <x:Property Name="arr_Slides" Type="InArgument(s:String[])" />
  </x:Members>
  <sap2010:WorkflowViewState.IdRef>ActivityBuilder_1</sap2010:WorkflowViewState.IdRef>
  <TextExpression.NamespacesForImplementation>
    <sco:Collection x:TypeArguments="x:String">
      <x:String>GlobalConstantsNamespace</x:String>
      <x:String>GlobalVariablesNamespace</x:String>
      <x:String>System</x:String>
      <x:String>System.Collections.Generic</x:String>
      <x:String>System.Collections.ObjectModel</x:String>
      <x:String>System.Linq</x:String>
      <x:String>Microsoft.VisualBasic</x:String>
      <x:String>UiPath.Core</x:String>
      <x:String>UiPath.Core.Activities</x:String>
    </sco:Collection>
  </TextExpression.NamespacesForImplementation>
  <TextExpression.ReferencesForImplementation>
    <sco:Collection x:TypeArguments="AssemblyReference">
      <AssemblyReference>System.ComponentModel.TypeConverter</AssemblyReference>
      <AssemblyReference>System.Linq</AssemblyReference>
      <AssemblyReference>System.ObjectModel</AssemblyReference>
      <AssemblyReference>Microsoft.VisualBasic</AssemblyReference>
      <AssemblyReference>UiPath.System.Activities</AssemblyReference>
      <AssemblyReference>UiPath.UiAutomation.Activities</AssemblyReference>
    </sco:Collection>
  </TextExpression.ReferencesForImplementation>
  <Sequence DisplayName="AI Interactive Presenter" sap:VirtualizedContainerService.HintSize="600,200" sap2010:WorkflowViewState.IdRef="Sequence_Main">
{variables_block}
    <sap:WorkflowViewStateService.ViewState>
      <scg:Dictionary x:TypeArguments="x:String, x:Object">
        <x:Boolean x:Key="IsExpanded">True</x:Boolean>
      </scg:Dictionary>
    </sap:WorkflowViewStateService.ViewState>
    <ui:InvokeWorkflowFile ArgumentsVariable="{{x:Null}}" DisplayName="Init and prepare (config, pipeline, slides)" sap:VirtualizedContainerService.HintSize="600,200" sap2010:WorkflowViewState.IdRef="Invoke_InitPrepare" LogEntry="No" LogExit="No" UnSafe="False" WorkflowFileName="Workflows\\AIPresenter\\AIPresenter_InitAndPrepare.xaml">
      <ui:InvokeWorkflowFile.Arguments>
{init_xml}
      </ui:InvokeWorkflowFile.Arguments>
    </ui:InvokeWorkflowFile>
    <ui:ForEach x:TypeArguments="x:String" CurrentIndex="{{x:Null}}" DisplayName="Slide loop (slides.csv order)" sap:VirtualizedContainerService.HintSize="600,200" sap2010:WorkflowViewState.IdRef="ForEach_Slides" Values="[If(System.IO.File.Exists(str_SlidesIterateTsv), System.IO.File.ReadAllLines(str_SlidesIterateTsv).Where(Function(l) Not String.IsNullOrWhiteSpace(l)).ToArray(), New String() {{}})]">
      <ui:ForEach.Body>
        <ActivityAction x:TypeArguments="x:String">
          <ActivityAction.Argument>
            <DelegateInArgument x:TypeArguments="x:String" Name="slideItem" />
          </ActivityAction.Argument>
          <ui:InvokeWorkflowFile ArgumentsVariable="{{x:Null}}" DisplayName="Process one slide (image + narration)" sap:VirtualizedContainerService.HintSize="600,200" sap2010:WorkflowViewState.IdRef="Invoke_SlideIteration" LogEntry="No" LogExit="No" UnSafe="False" WorkflowFileName="Workflows\\AIPresenter\\AIPresenter_SlideIteration.xaml">
            <ui:InvokeWorkflowFile.Arguments>
{slide_xml}
            </ui:InvokeWorkflowFile.Arguments>
          </ui:InvokeWorkflowFile>
        </ActivityAction>
      </ui:ForEach.Body>
    </ui:ForEach>
    <ui:InvokeWorkflowFile ArgumentsVariable="{{x:Null}}" DisplayName="After slides: video then Q&amp;A" sap:VirtualizedContainerService.HintSize="600,200" sap2010:WorkflowViewState.IdRef="Invoke_AfterPresentation" LogEntry="No" LogExit="No" UnSafe="False" WorkflowFileName="Workflows\\AIPresenter\\AIPresenter_AfterPresentation.xaml">
      <ui:InvokeWorkflowFile.Arguments>
{after_xml}
      </ui:InvokeWorkflowFile.Arguments>
    </ui:InvokeWorkflowFile>
  </Sequence>
</Activity>
'''
    main_path.write_text(main, encoding="utf-8", newline="\n")
    print("Written:", main_path)


if __name__ == "__main__":
    main()
