<a name=".aea.protocols.default.serialization"></a>
## aea.protocols.default.serialization

Serialization module for default protocol.

<a name=".aea.protocols.default.serialization.DefaultSerializer"></a>
### DefaultSerializer

```python
class DefaultSerializer(Serializer)
```

Serialization for the 'default' protocol.

<a name=".aea.protocols.default.serialization.DefaultSerializer.encode"></a>
#### encode

```python
 | encode(msg: Message) -> bytes
```

Encode a 'Default' message into bytes.

**Arguments**:

- `msg`: the message object.

**Returns**:

the bytes.

<a name=".aea.protocols.default.serialization.DefaultSerializer.decode"></a>
#### decode

```python
 | decode(obj: bytes) -> Message
```

Decode bytes into a 'Default' message.

**Arguments**:

- `obj`: the bytes object.

**Returns**:

the 'Default' message.

