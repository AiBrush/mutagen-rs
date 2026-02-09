"""mutagen_rs.id3 - ID3 tag handler.

Drop-in replacement for mutagen.id3.
"""
from . import (
    # Tag container
    ID3,
    # Encoding enum
    Encoding,
    # Errors
    ID3Error,
    ID3NoHeaderError,
    MutagenError,
    PaddingInfo,
    # Enums and support types
    PictureType,
    CTOCFlags,
    ID3v1SaveOptions,
    ID3TimeStamp,
    # Frame base classes
    Frame,
    TextFrame,
    NumericTextFrame,
    NumericPartTextFrame,
    TimeStampTextFrame,
    UrlFrame,
    UrlFrameU,
    PairedTextFrame,
    BinaryFrame,
    # All v2.3/v2.4 frame classes
    TALB, TBPM, TCOM, TCON, TCOP, TCMP, TDAT, TDEN, TDES, TKWD, TCAT,
    MVNM, MVIN, GRP1, TDOR, TDLY, TDRC, TDRL, TDTG, TENC, TEXT, TFLT,
    TGID, TIME, TIT1, TIT2, TIT3, TKEY, TLAN, TLEN, TMED, TMOO, TOAL,
    TOFN, TOLY, TOPE, TORY, TOWN, TPE1, TPE2, TPE3, TPE4, TPOS, TPRO,
    TPUB, TRCK, TRDA, TRSN, TRSO, TSIZ, TSO2, TSOA, TSOC, TSOP, TSOT,
    TSRC, TSSE, TSST, TYER, TXXX,
    WCOM, WCOP, WFED, WOAF, WOAR, WOAS, WORS, WPAY, WPUB, WXXX,
    TIPL, TMCL, IPLS,
    APIC, USLT, SYLT, COMM, RVA2, EQU2, RVAD, RVRB, POPM, PCNT, PCST,
    GEOB, RBUF, AENC, LINK, POSS, UFID, USER, OWNE, COMR, ENCR, GRID,
    PRIV, SIGN, SEEK, ASPI, MCDI, ETCO, MLLT, SYTC, CRM, CHAP, CTOC,
    # v2.2 aliases
    UFI, TT1, TT2, TT3, TP1, TP2, TP3, TP4, TCM, TXT, TLA, TCO, TAL,
    TPA, TRK, TRC, TYE, TDA, TIM, TRD, TMT, TFT, TBP, TCP, TCR, TPB,
    TEN, TST, TSA, TS2, TSP, TSC, TSS, TOF, TLE, TSI, TDY, TKE, TOT,
    TOA, TOL, TOR, TXX, WAF, WAR, WAS, WCM, WCP, WPB, WXX, IPL, MCI,
    ETC, MLL, STC, ULT, SLT, COM, RVA, REV, PIC, GEO, CNT, POP, BUF,
    CRA, LNK, MVN, MVI, GP1,
    # Frame dicts
    Frames, Frames_2_2,
)

# mutagen.id3 also exports Open = ID3
Open = ID3

__all__ = [
    'ID3', 'Open', 'Encoding', 'ID3Error', 'ID3NoHeaderError', 'MutagenError',
    'PaddingInfo', 'PictureType', 'CTOCFlags', 'ID3v1SaveOptions', 'ID3TimeStamp',
    'Frame', 'TextFrame', 'NumericTextFrame', 'NumericPartTextFrame',
    'TimeStampTextFrame', 'UrlFrame', 'UrlFrameU', 'PairedTextFrame', 'BinaryFrame',
    'Frames', 'Frames_2_2',
    # All frame class names are also exported
    'TALB', 'TBPM', 'TCOM', 'TCON', 'TCOP', 'TCMP', 'TDAT', 'TDEN', 'TDES',
    'TKWD', 'TCAT', 'MVNM', 'MVIN', 'GRP1', 'TDOR', 'TDLY', 'TDRC', 'TDRL',
    'TDTG', 'TENC', 'TEXT', 'TFLT', 'TGID', 'TIME', 'TIT1', 'TIT2', 'TIT3',
    'TKEY', 'TLAN', 'TLEN', 'TMED', 'TMOO', 'TOAL', 'TOFN', 'TOLY', 'TOPE',
    'TORY', 'TOWN', 'TPE1', 'TPE2', 'TPE3', 'TPE4', 'TPOS', 'TPRO', 'TPUB',
    'TRCK', 'TRDA', 'TRSN', 'TRSO', 'TSIZ', 'TSO2', 'TSOA', 'TSOC', 'TSOP',
    'TSOT', 'TSRC', 'TSSE', 'TSST', 'TYER', 'TXXX',
    'WCOM', 'WCOP', 'WFED', 'WOAF', 'WOAR', 'WOAS', 'WORS', 'WPAY', 'WPUB', 'WXXX',
    'TIPL', 'TMCL', 'IPLS',
    'APIC', 'USLT', 'SYLT', 'COMM', 'RVA2', 'EQU2', 'RVAD', 'RVRB',
    'POPM', 'PCNT', 'PCST', 'GEOB', 'RBUF', 'AENC', 'LINK', 'POSS',
    'UFID', 'USER', 'OWNE', 'COMR', 'ENCR', 'GRID', 'PRIV', 'SIGN',
    'SEEK', 'ASPI', 'MCDI', 'ETCO', 'MLLT', 'SYTC', 'CRM', 'CHAP', 'CTOC',
]
