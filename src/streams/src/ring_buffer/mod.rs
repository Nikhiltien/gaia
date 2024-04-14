#[derive(Debug)]
pub struct RingBuffer<T, const SIZE: usize> {
    buffer: [Option<T>; SIZE],
    head: usize,
    tail: usize,
    count: usize,
}

impl<T, const SIZE: usize> RingBuffer<T, SIZE> {
    pub fn new() -> Self {
        // Initialize the buffer by creating an array of None values.
        let buffer = {
            let mut temp_buf = std::mem::MaybeUninit::<[Option<T>; SIZE]>::uninit();
            let temp_buf_ptr = temp_buf.as_mut_ptr();

            // Initialize each element of the array with None.
            for i in 0..SIZE {
                unsafe {
                    std::ptr::write(temp_buf_ptr.cast::<Option<T>>().add(i), None);
                }
            }

            unsafe { temp_buf.assume_init() }
        };

        RingBuffer {
            buffer,
            head: 0,
            tail: 0,
            count: 0,
        }
    }

    pub fn push(&mut self, item: T) -> Option<T> {
        let old = std::mem::replace(&mut self.buffer[self.tail], Some(item));

        self.tail = (self.tail + 1) % SIZE;
        if self.count < SIZE {
            self.count += 1;
        } else {
            // Buffer is full, move the head forward to maintain the ring
            self.head = (self.head + 1) % SIZE;
        }

        old
    }

    pub fn pop(&mut self) -> Option<T> {
        if self.is_empty() {
            None
        } else {
            let result = self.buffer[self.head].take();
            self.head = (self.head + 1) % SIZE;
            self.count -= 1;
            result
        }
    }

    pub fn peek(&self) -> Option<&T> {
        self.buffer[self.head].as_ref()
    }

    pub fn peek_mut(&mut self) -> Option<&mut T> {
        self.buffer[self.head].as_mut()
    }

    pub fn is_empty(&self) -> bool {
        self.count == 0
    }

    pub fn is_full(&self) -> bool {
        self.count == SIZE
    }
}

#[cfg(test)]
mod tests {
    use super::RingBuffer;

    #[test]
    fn insert_into_empty_buffer() {
        let mut buffer: RingBuffer<i32, 5> = RingBuffer::new(); // Specify the size as a generic parameter
        assert!(buffer.is_empty());
        buffer.push(1);
        assert!(!buffer.is_empty());
    }

    #[test]
    fn continuous_insertions_fill_buffer() {
        let mut buffer: RingBuffer<i32, 3> = RingBuffer::new(); // Capacity is part of the type
        buffer.push(1);
        buffer.push(2);
        buffer.push(3);
        buffer.push(4); // This should overwrite 1
        assert_eq!(buffer.pop().unwrap(), 2);
        assert_eq!(buffer.pop().unwrap(), 3);
        assert_eq!(buffer.pop().unwrap(), 4);
        assert!(buffer.is_empty());
    }

    #[test]
    fn overwrite_old_values() {
        let mut buffer: RingBuffer<i32, 2> = RingBuffer::new();
        buffer.push(1);
        buffer.push(2);
        buffer.push(3); // This should overwrite 1
        assert_eq!(buffer.pop().unwrap(), 2);
        assert_eq!(buffer.pop().unwrap(), 3);
        assert!(buffer.is_empty());
    }

    #[test]
    fn pop_from_empty_buffer() {
        let mut buffer: RingBuffer<i32, 1> = RingBuffer::new(); // Correctly initialize with size
        assert!(buffer.pop().is_none());
    }
}
