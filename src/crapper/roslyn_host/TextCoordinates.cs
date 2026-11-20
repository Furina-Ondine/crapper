using System.Text;
using Microsoft.CodeAnalysis.Text;

namespace UbMode.RoslynHost;

internal sealed class TextCoordinates
{
    private readonly SourceText text;
    private readonly int[] bytes;

    public TextCoordinates(string source)
    {
        text = SourceText.From(source, Encoding.UTF8);
        bytes = new int[source.Length + 1];
        for (var index = 0; index < source.Length;)
        {
            var rune = Rune.GetRuneAt(source, index);
            var next = index + rune.Utf16SequenceLength;
            Array.Fill(bytes, bytes[index], index, rune.Utf16SequenceLength);
            bytes[next] = bytes[index] + rune.Utf8SequenceLength;
            index = next;
        }
    }

    public int Byte(int position) => bytes[position];

    public (int Line, int Column) Point(int position)
    {
        var point = text.Lines.GetLinePosition(position);
        return (point.Line + 1, bytes[position] - bytes[text.Lines[point.Line].Start]);
    }

    // Executable units always contain tokens, so their last source position exists.
    public int InclusiveEndLine(TextSpan span) => Point(span.End - 1).Line;
}
