# Applies ST-DBP-002 fix: max 3 workflow arguments (session dictionaries + headers).
# Run: py apply_session_dictionary_args.py
from pathlib import Path
import re

ROOT = Path(r"c:\Users\Admin\Documents\UiPath\NHOP Project")
_SCRIPTS = Path(__file__).resolve().parent
WF = ROOT / "Workflows" / "AIPresenter"
INIT = WF / "AIPresenter_InitAndPrepare.xaml"
AFTER = WF / "AIPresenter_AfterPresentation.xaml"
# Q&A body slice for rebuilding AfterPresentation (not a UiPath workflow; avoids ST-DBP-002 on a standalone QA file)
QA_INLINE_FRAGMENT = _SCRIPTS / "_qa_inline_fragment.xml"
MAIN = ROOT / "AIInteractivePresenter.xaml"

MEMBERS_3 = """  <x:Members>
    <x:Property Name="io_SessionStrings" Type="InOutArgument(scg:Dictionary(x:String, x:String))" />
    <x:Property Name="io_SessionInts" Type="InOutArgument(scg:Dictionary(x:String, x:Int32))" />
    <x:Property Name="dict_Headers" Type="InOutArgument(scg:Dictionary(x:String, x:String))" />
  </x:Members>"""

INIT_STRING_KEYS = [
    "str_OpenAIKey", "str_ElevenLabsKey", "str_VoiceId", "str_MicrophoneName",
    "str_ResolveMicScriptPath", "str_ResolvedMicFile", "str_OpenDefaultAppScript",
    "str_PlayResponseAudioScript", "str_PlayVideoScript", "str_SlidesFromCsvScript",
    "str_SlidesIterateTsv", "str_PipelineScript", "str_NarrationAudioPath",
    "str_FfmpegPath", "str_WavInputPath", "str_AudioPath", "str_SlideVideoPath",
    "str_SlidePrompt", "str_GlobalSlideContext", "str_GptComposedSlides", "str_PythonExe",
]
INIT_INT_KEYS = ["int_SlidesCsvShellResult", "int_PipelineShellResult"]


def init_unpack_assigns() -> str:
    lines = []
    for k in INIT_STRING_KEYS:
        lines.append(f"""      <Assign DisplayName="Unpack {k}" sap:VirtualizedContainerService.HintSize="416,82.4" sap2010:WorkflowViewState.IdRef="Unpack_{k}">
        <Assign.To>
          <OutArgument x:TypeArguments="x:String">[{k}]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="x:String">[If(io_SessionStrings IsNot Nothing AndAlso io_SessionStrings.ContainsKey(&quot;{k}&quot;), io_SessionStrings(&quot;{k}&quot;), &quot;&quot;)]</InArgument>
        </Assign.Value>
      </Assign>""")
    lines.append("""      <Assign DisplayName="Unpack bln_UseWindowsDefaultMic" sap:VirtualizedContainerService.HintSize="416,82.4" sap2010:WorkflowViewState.IdRef="Unpack_blnMic">
        <Assign.To>
          <OutArgument x:TypeArguments="x:Boolean">[bln_UseWindowsDefaultMic]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="x:Boolean">[If(io_SessionStrings IsNot Nothing AndAlso io_SessionStrings.ContainsKey(&quot;bln_UseWindowsDefaultMic&quot;), Boolean.Parse(io_SessionStrings(&quot;bln_UseWindowsDefaultMic&quot;)), False)]</InArgument>
        </Assign.Value>
      </Assign>""")
    for k in INIT_INT_KEYS:
        lines.append(f"""      <Assign DisplayName="Unpack {k}" sap:VirtualizedContainerService.HintSize="416,82.4" sap2010:WorkflowViewState.IdRef="Unpack_{k}">
        <Assign.To>
          <OutArgument x:TypeArguments="x:Int32">[{k}]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="x:Int32">[If(io_SessionInts IsNot Nothing AndAlso io_SessionInts.ContainsKey(&quot;{k}&quot;), io_SessionInts(&quot;{k}&quot;), 0)]</InArgument>
        </Assign.Value>
      </Assign>""")
    return "\n".join(lines)


def _vb_from_pairs(keys: list[str]) -> str:
    return ", ".join(['{{"' + k + '", ' + k + '}}' for k in keys])


def init_pack_assign() -> str:
    pairs = _vb_from_pairs(INIT_STRING_KEYS)
    pairs += ', {{"bln_UseWindowsDefaultMic", bln_UseWindowsDefaultMic.ToString}}'
    int_pairs = _vb_from_pairs(INIT_INT_KEYS)
    return f"""      <Assign DisplayName="Pack io_SessionStrings (return to caller)" sap:VirtualizedContainerService.HintSize="416,82.4" sap2010:WorkflowViewState.IdRef="Pack_SessionStrings">
        <Assign.To>
          <OutArgument x:TypeArguments="scg:Dictionary(x:String, x:String)">[io_SessionStrings]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="scg:Dictionary(x:String, x:String)">[New Dictionary(Of String, String) From {pairs}]</InArgument>
        </Assign.Value>
      </Assign>
      <Assign DisplayName="Pack io_SessionInts (return to caller)" sap:VirtualizedContainerService.HintSize="416,82.4" sap2010:WorkflowViewState.IdRef="Pack_SessionInts">
        <Assign.To>
          <OutArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)">[io_SessionInts]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)">[New Dictionary(Of String, Int32) From {int_pairs}]</InArgument>
        </Assign.Value>
      </Assign>"""


def init_sequence_variables() -> str:
    vars_xml = [
        '      <Variable x:TypeArguments="x:String" Name="str_SettingsPath" />',
        '      <Variable x:TypeArguments="x:String" Name="str_SettingsJson" />',
    ]
    for k in INIT_STRING_KEYS:
        d = ""
        if k == "str_OpenAIKey":
            d = ' Default="YOUR_OPENAI_API_KEY"'
        elif k == "str_ElevenLabsKey":
            d = ' Default="YOUR_ELEVENLABS_API_KEY"'
        elif k == "str_VoiceId":
            d = ' Default="YOUR_VOICE_ID"'
        elif k == "str_MicrophoneName":
            d = ' Default="Microphone Name"'
        elif k == "str_FfmpegPath":
            d = ' Default="ffmpeg"'
        elif k == "str_WavInputPath":
            d = ' Default="Data\\AIPresenter\\Temp\\output.wav"'
        elif k == "str_AudioPath":
            d = ' Default="Data\\AIPresenter\\Temp\\response.wav"'
        vars_xml.append(f'      <Variable x:TypeArguments="x:String"{d} Name="{k}" />')
    vars_xml.append('      <Variable x:TypeArguments="x:Boolean" Default="False" Name="bln_UseWindowsDefaultMic" />')
    for k in INIT_INT_KEYS:
        vars_xml.append(f'      <Variable x:TypeArguments="x:Int32" Default="0" Name="{k}" />')
    return "\n".join(vars_xml)


def patch_init():
    text = INIT.read_text(encoding="utf-8")
    if "io_SessionStrings" in text and "Pack io_SessionStrings (return" in text:
        print("Init already patched, skip")
        return
    text = re.sub(r"  <x:Members>.*?</x:Members>\s*", MEMBERS_3 + "\n", text, count=1, flags=re.DOTALL)
    sv0 = text.index("<Sequence.Variables>")
    sv1 = text.index("</Sequence.Variables>", sv0) + len("</Sequence.Variables>")
    text = text[:sv0] + "<Sequence.Variables>\n" + init_sequence_variables() + "\n    </Sequence.Variables>" + text[sv1:]
    unpack = init_unpack_assigns()
    pack = init_pack_assign()
    text = text.replace(
        "</Sequence.Variables>\n",
        "</Sequence.Variables>\n" + unpack + "\n",
        1,
    )
    if "Pack io_SessionStrings" not in text:
        text = text.replace(
            "      </If>\n  </Sequence>\n</Activity>",
            "      </If>\n" + pack + "\n  </Sequence>\n</Activity>",
            1,
        )
    INIT.write_text(text, encoding="utf-8", newline="\n")
    print("Patched", INIT)


AFTER_STRING_KEYS = [
    "str_SlideVideoPath", "str_GptComposedSlides", "str_PythonExe", "str_PlayVideoScript", "str_FfmpegPath",
    "str_UserQuestionChoice", "str_CurrentSlideContent", "str_ResolveMicScriptPath", "str_ResolvedMicFile",
    "str_MicrophoneName", "str_RecordInputArgs", "str_FfmpegArgLine", "str_FfmpegRecordExeFile",
    "str_FfmpegRecordArgFile", "str_FfmpegRecordPidFile", "str_StartFfmpegScript", "str_StopFfmpegScript",
    "str_WavInputPath", "str_WhisperJsonBody", "str_WhisperResponse", "str_OpenAIKey", "str_GptUserContent",
    "str_GptJsonBody", "str_AIResponse", "str_SlidePrompt", "str_ElevenJsonBody", "str_ElevenResponseRaw",
    "str_AudioPath", "str_PlayResponseAudioScript", "str_ElevenLabsKey", "str_VoiceId",
]
AFTER_INT_KEYS = [
    "int_PlaySlideVideoShellResult", "int_PlayResponseShellResult", "int_SlidesCsvShellResult",
    "int_PipelineShellResult", "int_QaSlideOrdinal",
]


def after_unpack() -> str:
    lines = []
    for k in AFTER_STRING_KEYS:
        lines.append(f"""      <Assign DisplayName="Unpack {k}" sap:VirtualizedContainerService.HintSize="200,82.4" sap2010:WorkflowViewState.IdRef="UnpackAP_{k}">
        <Assign.To>
          <OutArgument x:TypeArguments="x:String">[{k}]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="x:String">[If(io_SessionStrings IsNot Nothing AndAlso io_SessionStrings.ContainsKey(&quot;{k}&quot;), io_SessionStrings(&quot;{k}&quot;), &quot;&quot;)]</InArgument>
        </Assign.Value>
      </Assign>""")
    lines.append("""      <Assign DisplayName="Unpack bln_UseWindowsDefaultMic" sap:VirtualizedContainerService.HintSize="200,82.4" sap2010:WorkflowViewState.IdRef="UnpackAP_bln">
        <Assign.To>
          <OutArgument x:TypeArguments="x:Boolean">[bln_UseWindowsDefaultMic]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="x:Boolean">[If(io_SessionStrings IsNot Nothing AndAlso io_SessionStrings.ContainsKey(&quot;bln_UseWindowsDefaultMic&quot;), Boolean.Parse(io_SessionStrings(&quot;bln_UseWindowsDefaultMic&quot;)), False)]</InArgument>
        </Assign.Value>
      </Assign>""")
    for k in AFTER_INT_KEYS:
        lines.append(f"""      <Assign DisplayName="Unpack {k}" sap:VirtualizedContainerService.HintSize="200,82.4" sap2010:WorkflowViewState.IdRef="UnpackAP_{k}">
        <Assign.To>
          <OutArgument x:TypeArguments="x:Int32">[{k}]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="x:Int32">[If(io_SessionInts IsNot Nothing AndAlso io_SessionInts.ContainsKey(&quot;{k}&quot;), io_SessionInts(&quot;{k}&quot;), 0)]</InArgument>
        </Assign.Value>
      </Assign>""")
    return "\n".join(lines)


def after_pack() -> str:
    pairs = _vb_from_pairs(AFTER_STRING_KEYS)
    pairs += ', {{"bln_UseWindowsDefaultMic", bln_UseWindowsDefaultMic.ToString}}'
    int_pairs = _vb_from_pairs(AFTER_INT_KEYS)
    return f"""      <Assign DisplayName="Pack io_SessionStrings" sap:VirtualizedContainerService.HintSize="200,82.4" sap2010:WorkflowViewState.IdRef="PackAP_SessionStrings">
        <Assign.To>
          <OutArgument x:TypeArguments="scg:Dictionary(x:String, x:String)">[io_SessionStrings]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="scg:Dictionary(x:String, x:String)">[New Dictionary(Of String, String) From {pairs}]</InArgument>
        </Assign.Value>
      </Assign>
      <Assign DisplayName="Pack io_SessionInts" sap:VirtualizedContainerService.HintSize="200,82.4" sap2010:WorkflowViewState.IdRef="PackAP_SessionInts">
        <Assign.To>
          <OutArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)">[io_SessionInts]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)">[New Dictionary(Of String, Int32) From {int_pairs}]</InArgument>
        </Assign.Value>
      </Assign>"""


def after_sequence_variables() -> str:
    parts = []
    for k in AFTER_STRING_KEYS:
        d = ""
        if k == "str_AudioPath":
            d = ' Default="Data\\AIPresenter\\Temp\\response.wav"'
        elif k == "str_WavInputPath":
            d = ' Default="Data\\AIPresenter\\Temp\\output.wav"'
        elif k == "str_PythonExe":
            d = ' Default="pyw"'
        parts.append(f'      <Variable x:TypeArguments="x:String"{d} Name="{k}" />')
    parts.append('      <Variable x:TypeArguments="x:Boolean" Default="False" Name="bln_UseWindowsDefaultMic" />')
    for k in AFTER_INT_KEYS:
        dv = "-1" if k == "int_QaSlideOrdinal" else "0"
        parts.append(f'      <Variable x:TypeArguments="x:Int32" Default="{dv}" Name="{k}" />')
    return "\n".join(parts)


def patch_after_with_inline_qa():
    qa_inner = QA_INLINE_FRAGMENT.read_text(encoding="utf-8")
    if "Resolve current default mic" not in qa_inner or "Whisper STT" not in qa_inner:
        raise SystemExit("Q&A fragment (_qa_inline_fragment.xml) looks wrong or truncated")

    head = """<Activity mc:Ignorable="sap sap2010" x:Class="AIPresenter_AfterPresentation" xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:s="clr-namespace:System;assembly=System.Private.CoreLib" xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation" xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation" xmlns:scg="clr-namespace:System.Collections.Generic;assembly=System.Private.CoreLib" xmlns:sco="clr-namespace:System.Collections.ObjectModel;assembly=System.Private.CoreLib" xmlns:ui="http://schemas.uipath.com/workflow/activities" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
""" + MEMBERS_3 + """
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
  <Sequence DisplayName="After slides: video then Q&amp;A" sap:VirtualizedContainerService.HintSize="200,200" sap2010:WorkflowViewState.IdRef="Sequence_AfterSlides">
    <Sequence.Variables>
""" + after_sequence_variables() + """
    </Sequence.Variables>
""" + after_unpack() + """
      <If Condition="[Not String.IsNullOrWhiteSpace(str_SlideVideoPath) AndAlso System.IO.File.Exists(str_SlideVideoPath)]" sap:VirtualizedContainerService.HintSize="200,200" sap2010:WorkflowViewState.IdRef="If_PlaySlideVideo">
        <If.Then>
          <Assign sap:VirtualizedContainerService.HintSize="200,200" sap2010:WorkflowViewState.IdRef="Assign_PlaySlideVideoShell">
            <Assign.To>
              <OutArgument x:TypeArguments="x:Int32">[int_PlaySlideVideoShellResult]</OutArgument>
            </Assign.To>
            <Assign.Value>
              <InArgument x:TypeArguments="x:Int32">[Microsoft.VisualBasic.Interaction.Shell(Chr(34) + str_PythonExe + Chr(34) + &quot; &quot; + Chr(34) + str_PlayVideoScript + Chr(34) + &quot; --path &quot; + Chr(34) + str_SlideVideoPath + Chr(34) + &quot; --ffmpeg &quot; + Chr(34) + str_FfmpegPath + Chr(34), Microsoft.VisualBasic.AppWinStyle.MinimizedNoFocus, True)]</InArgument>
            </Assign.Value>
          </Assign>
        </If.Then>
      </If>
      <Assign sap:VirtualizedContainerService.HintSize="200,200" sap2010:WorkflowViewState.IdRef="Assign_QAContextAfterPresentation">
        <Assign.To>
          <OutArgument x:TypeArguments="x:String">[str_CurrentSlideContent]</OutArgument>
        </Assign.To>
        <Assign.Value>
          <InArgument x:TypeArguments="x:String">[&quot;Presentation notes (all slides):&quot; + Environment.NewLine + Environment.NewLine + str_GptComposedSlides]</InArgument>
        </Assign.Value>
      </Assign>
      <ui:MessageBox Caption="{x:Null}" AutoCloseAfter="00:00:00" Buttons="YesNo" DisplayName="After presentation — any questions?" sap:VirtualizedContainerService.HintSize="200,200" sap2010:WorkflowViewState.IdRef="MessageBox_AfterPresentation" Text="After the presentation — do you have any questions?" TopMost="True" ChosenButton="[str_UserQuestionChoice]" />
      <If Condition="[str_UserQuestionChoice.Trim.ToLower = &quot;yes&quot; OrElse str_UserQuestionChoice.Trim.ToLower = &quot;y&quot;]" sap:VirtualizedContainerService.HintSize="200,200" sap2010:WorkflowViewState.IdRef="If_UserWantsQA_AfterPresentation">
        <If.Then>
""" + qa_inner + """
        </If.Then>
      </If>
""" + after_pack() + """
  </Sequence>
</Activity>
"""
    AFTER.write_text(head, encoding="utf-8", newline="\n")
    print("Rewrote", AFTER, "(inline Q&A, 3 args)")


def build_main_pack_init_dict() -> str:
    pairs = _vb_from_pairs(INIT_STRING_KEYS)
    pairs += ', {{"bln_UseWindowsDefaultMic", bln_UseWindowsDefaultMic.ToString}}'
    int_pairs = _vb_from_pairs(INIT_INT_KEYS + ["int_PlaySlideVideoShellResult", "int_PlayResponseShellResult", "int_QaSlideOrdinal"])
    return f"""    <Assign DisplayName="Pack dicts before Init" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="Assign_PackBeforeInit">
      <Assign.To>
        <OutArgument x:TypeArguments="scg:Dictionary(x:String, x:String)">[dict_SessionStrings]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="scg:Dictionary(x:String, x:String)">[New Dictionary(Of String, String) From {pairs}]</InArgument>
      </Assign.Value>
    </Assign>
    <Assign DisplayName="Pack int dict before Init" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="Assign_PackIntsBeforeInit">
      <Assign.To>
        <OutArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)">[dict_SessionInts]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)">[New Dictionary(Of String, Int32) From {int_pairs}]</InArgument>
      </Assign.Value>
    </Assign>"""


def main_unpack_from_init() -> str:
    lines = []
    for k in INIT_STRING_KEYS:
        lines.append(f"""    <Assign DisplayName="Sync {k} after Init" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="SyncAfterInit_{k}">
      <Assign.To>
        <OutArgument x:TypeArguments="x:String">[{k}]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="x:String">[If(dict_SessionStrings IsNot Nothing AndAlso dict_SessionStrings.ContainsKey(&quot;{k}&quot;), dict_SessionStrings(&quot;{k}&quot;), {k})]</InArgument>
      </Assign.Value>
    </Assign>""")
    lines.append("""    <Assign DisplayName="Sync bln_UseWindowsDefaultMic after Init" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="SyncAfterInit_bln">
      <Assign.To>
        <OutArgument x:TypeArguments="x:Boolean">[bln_UseWindowsDefaultMic]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="x:Boolean">[If(dict_SessionStrings IsNot Nothing AndAlso dict_SessionStrings.ContainsKey(&quot;bln_UseWindowsDefaultMic&quot;), Boolean.Parse(dict_SessionStrings(&quot;bln_UseWindowsDefaultMic&quot;)), bln_UseWindowsDefaultMic)]</InArgument>
      </Assign.Value>
    </Assign>""")
    for k in INIT_INT_KEYS:
        lines.append(f"""    <Assign DisplayName="Sync {k} after Init" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="SyncAfterInit_{k}">
      <Assign.To>
        <OutArgument x:TypeArguments="x:Int32">[{k}]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="x:Int32">[If(dict_SessionInts IsNot Nothing AndAlso dict_SessionInts.ContainsKey(&quot;{k}&quot;), dict_SessionInts(&quot;{k}&quot;), {k})]</InArgument>
      </Assign.Value>
    </Assign>""")
    return "\n".join(lines)


def main_pack_before_after() -> str:
    pairs = _vb_from_pairs(AFTER_STRING_KEYS)
    pairs += ', {{"bln_UseWindowsDefaultMic", bln_UseWindowsDefaultMic.ToString}}'
    int_pairs = _vb_from_pairs(AFTER_INT_KEYS)
    return f"""    <Assign DisplayName="Pack dicts before AfterPresentation" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="Assign_PackBeforeAfter">
      <Assign.To>
        <OutArgument x:TypeArguments="scg:Dictionary(x:String, x:String)">[dict_SessionStrings]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="scg:Dictionary(x:String, x:String)">[New Dictionary(Of String, String) From {pairs}]</InArgument>
      </Assign.Value>
    </Assign>
    <Assign DisplayName="Pack int dict before AfterPresentation" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="Assign_PackIntsBeforeAfter">
      <Assign.To>
        <OutArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)">[dict_SessionInts]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)">[New Dictionary(Of String, Int32) From {int_pairs}]</InArgument>
      </Assign.Value>
    </Assign>"""


def main_unpack_after_after() -> str:
    keys = [k for k in AFTER_STRING_KEYS if k not in ("str_SlideVideoPath", "str_GptComposedSlides", "str_PythonExe", "str_PlayVideoScript", "str_FfmpegPath")]
    lines = []
    for k in keys:
        lines.append(f"""    <Assign DisplayName="Sync {k} after AfterPresentation" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="SyncAfterAfter_{k}">
      <Assign.To>
        <OutArgument x:TypeArguments="x:String">[{k}]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="x:String">[If(dict_SessionStrings IsNot Nothing AndAlso dict_SessionStrings.ContainsKey(&quot;{k}&quot;), dict_SessionStrings(&quot;{k}&quot;), {k})]</InArgument>
      </Assign.Value>
    </Assign>""")
    lines.append("""    <Assign DisplayName="Sync bln after AfterPresentation" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="SyncAfterAfter_bln">
      <Assign.To>
        <OutArgument x:TypeArguments="x:Boolean">[bln_UseWindowsDefaultMic]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="x:Boolean">[If(dict_SessionStrings IsNot Nothing AndAlso dict_SessionStrings.ContainsKey(&quot;bln_UseWindowsDefaultMic&quot;), Boolean.Parse(dict_SessionStrings(&quot;bln_UseWindowsDefaultMic&quot;)), bln_UseWindowsDefaultMic)]</InArgument>
      </Assign.Value>
    </Assign>""")
    for k in AFTER_INT_KEYS:
        lines.append(f"""    <Assign DisplayName="Sync {k} after AfterPresentation" sap:VirtualizedContainerService.HintSize="600,82.4" sap2010:WorkflowViewState.IdRef="SyncAfterAfter_{k}">
      <Assign.To>
        <OutArgument x:TypeArguments="x:Int32">[{k}]</OutArgument>
      </Assign.To>
      <Assign.Value>
        <InArgument x:TypeArguments="x:Int32">[If(dict_SessionInts IsNot Nothing AndAlso dict_SessionInts.ContainsKey(&quot;{k}&quot;), dict_SessionInts(&quot;{k}&quot;), {k})]</InArgument>
      </Assign.Value>
    </Assign>""")
    return "\n".join(lines)


def patch_main():
    text = MAIN.read_text(encoding="utf-8")
    if "dict_SessionStrings" in text and "io_SessionStrings" in text:
        print("Main already patched, skip")
        return
    text = text.replace(
        "</Sequence.Variables>",
        """      <Variable x:TypeArguments="scg:Dictionary(x:String, x:String)" Name="dict_SessionStrings" />
      <Variable x:TypeArguments="scg:Dictionary(x:String, x:Int32)" Name="dict_SessionInts" />
    </Sequence.Variables>""",
        1,
    )
    old_init = re.search(
        r"<ui:InvokeWorkflowFile[^>]*Invoke_InitPrepare.*?</ui:InvokeWorkflowFile>",
        text,
        re.DOTALL,
    )
    if not old_init:
        raise SystemExit("Init invoke not found")
    new_init = (
        build_main_pack_init_dict()
        + """
    <ui:InvokeWorkflowFile ArgumentsVariable="{x:Null}" DisplayName="Init and prepare (config, pipeline, slides)" sap:VirtualizedContainerService.HintSize="600,200" sap2010:WorkflowViewState.IdRef="Invoke_InitPrepare" LogEntry="No" LogExit="No" UnSafe="False" WorkflowFileName="Workflows\\AIPresenter\\AIPresenter_InitAndPrepare.xaml">
      <ui:InvokeWorkflowFile.Arguments>
            <InOutArgument x:TypeArguments="scg:Dictionary(x:String, x:String)" x:Key="io_SessionStrings">[dict_SessionStrings]</InOutArgument>
            <InOutArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)" x:Key="io_SessionInts">[dict_SessionInts]</InOutArgument>
            <InOutArgument x:TypeArguments="scg:Dictionary(x:String, x:String)" x:Key="dict_Headers">[dict_Headers]</InOutArgument>
      </ui:InvokeWorkflowFile.Arguments>
    </ui:InvokeWorkflowFile>
"""
        + main_unpack_from_init()
    )
    text = text.replace(old_init.group(0), new_init, 1)

    old_after = re.search(
        r"<ui:InvokeWorkflowFile[^>]*Invoke_AfterPresentation.*?</ui:InvokeWorkflowFile>",
        text,
        re.DOTALL,
    )
    if not old_after:
        raise SystemExit("After invoke not found")
    new_after = (
        main_pack_before_after()
        + """
    <ui:InvokeWorkflowFile ArgumentsVariable="{x:Null}" DisplayName="After slides: video then Q&amp;A" sap:VirtualizedContainerService.HintSize="600,200" sap2010:WorkflowViewState.IdRef="Invoke_AfterPresentation" LogEntry="No" LogExit="No" UnSafe="False" WorkflowFileName="Workflows\\AIPresenter\\AIPresenter_AfterPresentation.xaml">
      <ui:InvokeWorkflowFile.Arguments>
            <InOutArgument x:TypeArguments="scg:Dictionary(x:String, x:String)" x:Key="io_SessionStrings">[dict_SessionStrings]</InOutArgument>
            <InOutArgument x:TypeArguments="scg:Dictionary(x:String, x:Int32)" x:Key="io_SessionInts">[dict_SessionInts]</InOutArgument>
            <InOutArgument x:TypeArguments="scg:Dictionary(x:String, x:String)" x:Key="dict_Headers">[dict_Headers]</InOutArgument>
      </ui:InvokeWorkflowFile.Arguments>
    </ui:InvokeWorkflowFile>
"""
        + main_unpack_after_after()
    )
    text = text.replace(old_after.group(0), new_after, 1)

    MAIN.write_text(text, encoding="utf-8", newline="\n")
    print("Patched", MAIN)


if __name__ == "__main__":
    patch_init()
    patch_after_with_inline_qa()
    patch_main()
    print("Done. Q&A inline source: Data/AIPresenter/Scripts/_qa_inline_fragment.xml")
