# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: src/zeromq/data.proto
# Protobuf Python Version: 4.25.3
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x15src/zeromq/data.proto\"u\n\tPriceData\x12\x10\n\x06symbol\x18\x01 \x01(\tH\x00\x12%\n\x0cknown_symbol\x18\x04 \x01(\x0e\x32\r.KnownSymbolsH\x00\x12\r\n\x05price\x18\x02 \x01(\x01\x12\x11\n\ttimestamp\x18\x03 \x01(\x03\x42\r\n\x0bsymbol_type\"w\n\nVolumeData\x12\x10\n\x06symbol\x18\x01 \x01(\tH\x00\x12%\n\x0cknown_symbol\x18\x04 \x01(\x0e\x32\r.KnownSymbolsH\x00\x12\x0e\n\x06volume\x18\x02 \x01(\x01\x12\x11\n\ttimestamp\x18\x03 \x01(\x03\x42\r\n\x0bsymbol_type\"-\n\x0eOrderBookEntry\x12\r\n\x05price\x18\x01 \x01(\x01\x12\x0c\n\x04size\x18\x02 \x01(\x01\"\x8a\x01\n\rOrderBookData\x12\x0e\n\x06symbol\x18\x01 \x01(\t\x12\x1d\n\x04\x62ids\x18\x02 \x03(\x0b\x32\x0f.OrderBookEntry\x12\x1d\n\x04\x61sks\x18\x03 \x03(\x0b\x32\x0f.OrderBookEntry\x12\x18\n\x10last_trade_price\x18\x04 \x01(\x01\x12\x11\n\ttimestamp\x18\x05 \x01(\x03*7\n\x0cKnownSymbols\x12\x0b\n\x07UNKNOWN\x10\x00\x12\x0c\n\x08SYMBOL_A\x10\x01\x12\x0c\n\x08SYMBOL_B\x10\x02\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'src.zeromq.data_pb2', _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
  DESCRIPTOR._options = None
  _globals['_KNOWNSYMBOLS']._serialized_start=453
  _globals['_KNOWNSYMBOLS']._serialized_end=508
  _globals['_PRICEDATA']._serialized_start=25
  _globals['_PRICEDATA']._serialized_end=142
  _globals['_VOLUMEDATA']._serialized_start=144
  _globals['_VOLUMEDATA']._serialized_end=263
  _globals['_ORDERBOOKENTRY']._serialized_start=265
  _globals['_ORDERBOOKENTRY']._serialized_end=310
  _globals['_ORDERBOOKDATA']._serialized_start=313
  _globals['_ORDERBOOKDATA']._serialized_end=451
# @@protoc_insertion_point(module_scope)
