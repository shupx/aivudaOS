package com.aivuda.h16;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

final class Streams {
    private Streams() {}

    static String readUtf8(InputStream input) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = input.read(buffer)) != -1) bytes.write(buffer, 0, count);
        return bytes.toString("UTF-8");
    }
}
